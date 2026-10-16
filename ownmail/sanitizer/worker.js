#!/usr/bin/env node
"use strict";

/**
 * DOMPurify sanitization worker for ownmail.
 *
 * Long-lived process that reads newline-delimited JSON from stdin,
 * sanitizes HTML using DOMPurify + jsdom, and writes results to stdout.
 * CSS is parsed and scoped using postcss (proper AST, not regex).
 *
 * Protocol:
 *   Request:  {"id": 1, "html": "<div>...</div>"}
 *   Response: {"id": 1, "html": "<div>...</div>", "error": null}
 */

const { JSDOM } = require("jsdom");
const DOMPurify = require("dompurify");
const postcss = require("postcss");
const tokenizeCSS = require("postcss/lib/tokenize");

// Create a single jsdom window and DOMPurify instance (reused across requests)
const window = new JSDOM("").window;
const purify = DOMPurify(window);

// DOMPurify configuration
const PURIFY_CONFIG = {
  // Explicitly forbid dangerous elements
  FORBID_TAGS: [
    "script", "iframe", "object", "embed",
    "applet", "meta", "base",
    "math", "svg", "noscript",
    // Unwrapped: KEEP_CONTENT keeps the controls, which then have no form to submit
    "form",
    // "link" is NOT forbidden — we filter it in the uponSanitizeElement hook
  ],

  // Allow safe attributes
  FORBID_ATTR: [
    // Event handlers are blocked by DOMPurify by default,
    // but explicitly forbid dangerous attributes
    "xlink:href", "xmlns",
    // A control could otherwise join an application form by its id and
    // choose where and how that form submits
    "form", "formaction", "formenctype", "formmethod", "formnovalidate", "formtarget",
  ],

  // Allow data: URIs for inline images (CID replacements)
  ALLOW_DATA_ATTR: true,
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|data):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,

  // Allow <link> so we can filter it in the hook (trusted font stylesheets only)
  ADD_TAGS: ["link"],
  ADD_ATTR: ["rel", "href"],

  // Keep the full document structure so we can extract body content later
  WHOLE_DOCUMENT: true,
  // Return string, not DOM node
  RETURN_DOM: false,
  RETURN_DOM_FRAGMENT: false,
};

// Font providers whose stylesheets @import and <link> may load. A remote
// stylesheet escapes selector scoping, so no other host's is kept.
const TRUSTED_FONT_HOSTS = [
  "fonts.googleapis.com",
  "fonts.gstatic.com",
  "use.typekit.net",    // Adobe Fonts
  "p.typekit.net",
  "fast.fonts.net",     // Monotype
  "cloud.typography.com", // Hoefler
];

// Generic font family keywords (CSS spec)
const GENERIC_FONT_FAMILIES = new Set([
  "serif", "sans-serif", "monospace", "cursive", "fantasy",
  "system-ui", "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded",
  "math", "emoji", "fangsong",
]);

/**
 * If a font-family value doesn't end with a generic family, append sans-serif.
 */
function ensureFontFallback(value) {
  const priority = value.match(/\s*!\s*important\s*$/i);
  const family = priority ? value.slice(0, priority.index) : value;
  if (/^(inherit|initial|unset|revert|revert-layer)$/i.test(family.trim())) {
    return value;
  }
  // Split on commas, trim, and check the last entry
  const parts = family.split(",").map((s) => s.trim().replace(/['"]*/g, "").toLowerCase());
  const last = parts[parts.length - 1];
  if (last && GENERIC_FONT_FAMILIES.has(last)) {
    return value;
  }
  return family + ", sans-serif" + (priority ? priority[0] : "");
}

/**
 * Check if a URL is from a trusted font provider.
 */
function isTrustedFontUrl(url) {
  try {
    return TRUSTED_FONT_HOSTS.includes(new URL(url).hostname);
  } catch {
    return false;
  }
}

/**
 * Keep CSS strings and comments safe for an HTML style element without changing
 * their CSS meaning. Do this before PostCSS's own HTML escaping sees the text.
 */
function prepareStyleText(css) {
  const tokenizer = tokenizeCSS(new postcss.Input(css, { map: false }));
  const tokens = [];
  while (!tokenizer.endOfFile()) tokens.push(tokenizer.nextToken());

  // Legacy HTML comment wrappers are CSS tokens, not quoted/commented content.
  const last = tokens.filter((token) => token[0] !== "space").pop();
  const wrapped = /^\s*<!--/.test(css) && last && last[0] === "word" && last[1] === "-->";
  if (wrapped) last[1] = "";

  const result = tokens.map((token) => {
    if (token[0] === "string") {
      return token[1].replace(/\\[\s\S]|</g, (text) =>
        text === "<" || text === "\\<" ? "\\3c " : text
      );
    }
    if (token[0] === "comment") return token[1].replace(/</g, "\\3c ");
    return token[1];
  }).join("");
  return wrapped ? result.replace(/^(\s*)<!--/, "$1") : result;
}

// Browsers, not postcss, decide which rules message CSS contains. postcss
// continues strings across newlines and recognizes fewer url() forms, so a rule
// it reads as string or comment text can still reach the page. These helpers
// follow the browser tokenizer (https://drafts.csswg.org/css-syntax-3/#tokenization)
// for where tokens, blocks and comments begin and end, and for the decoded
// names, strings and URLs that decide what a rule is and what it loads.
const isDigit = (char) => char >= "0" && char <= "9";
const isHexDigit = (char) => isDigit(char) || (char >= "a" && char <= "f") || (char >= "A" && char <= "F");
const isWhitespace = (char) => char === " " || char === "\t" || char === "\n";
const isIdentStart = (char) => char !== undefined && (/[A-Za-z_]/.test(char) || char >= "\u0080");
const isIdentChar = (char) => isIdentStart(char) || isDigit(char) || char === "-";
const isNonPrintable = (char) => /[\x00-\x08\x0b\x0e-\x1f\x7f]/.test(char);
const BLOCK_ENDS = { "(": ")", "[": "]", "{": "}", function: ")" };

/** Apply the newline and NUL replacements a browser makes before tokenizing. */
function preprocessCSS(css) {
  return css.replace(/\r\n?|\f/g, "\n").replace(/\0/g, "\uFFFD");
}

/**
 * Tokenize preprocessed CSS. Comments are dropped. Names, strings and URLs
 * carry their decoded values, numbers their decoded unit.
 */
function cssTokens(css) {
  const tokens = [];
  let i = 0;
  const validEscape = (at) => css[at] === "\\" && css[at + 1] !== "\n";
  const startsIdent = (at) => (css[at] === "-"
    ? isIdentStart(css[at + 1]) || css[at + 1] === "-" || validEscape(at + 1)
    : isIdentStart(css[at]) || validEscape(at));
  const startsNumber = (at) => {
    if (css[at] === "+" || css[at] === "-") at++;
    return isDigit(css[at]) || (css[at] === "." && isDigit(css[at + 1]));
  };
  function escape() {
    let hex = "";
    for (i++; hex.length < 6 && isHexDigit(css[i]); i++) hex += css[i];
    if (hex) {
      if (isWhitespace(css[i])) i++;
      const code = parseInt(hex, 16);
      return code === 0 || (code >= 0xd800 && code <= 0xdfff) || code > 0x10ffff
        ? "\uFFFD" : String.fromCodePoint(code);
    }
    if (i >= css.length) return "\uFFFD";
    const char = String.fromCodePoint(css.codePointAt(i));
    i += char.length;
    return char;
  }
  function identSequence() {
    let value = "";
    for (;;) {
      if (isIdentChar(css[i])) value += css[i++];
      else if (validEscape(i)) value += escape();
      else return value;
    }
  }

  while (i < css.length) {
    const start = i;
    const char = css[i];
    let type = char;
    let value = char;
    if (char === "/" && css[i + 1] === "*") {
      const end = css.indexOf("*/", i + 2);
      i = end < 0 ? css.length : end + 2;
      continue;
    } else if (isWhitespace(char)) {
      while (isWhitespace(css[i])) i++;
      type = "whitespace";
    } else if (char === '"' || char === "'") {
      // An unescaped newline ends the string; the rest of the line is CSS again.
      type = "string";
      value = "";
      for (i++; i < css.length; ) {
        if (css[i] === char) {
          i++;
          break;
        }
        if (css[i] === "\n") {
          type = "bad-string";
          break;
        }
        if (css[i] !== "\\") value += css[i++];
        else if (i + 1 === css.length) i++;
        else if (css[i + 1] === "\n") i += 2;
        else value += escape();
      }
    } else if (char === "#" && (isIdentChar(css[i + 1]) || validEscape(i + 1))) {
      i++;
      type = "hash";
      value = identSequence();
    } else if (char === "@" && startsIdent(i + 1)) {
      i++;
      type = "at-keyword";
      value = identSequence();
    } else if (startsNumber(i)) {
      if (char === "+" || char === "-") i++;
      while (isDigit(css[i])) i++;
      if (css[i] === "." && isDigit(css[i + 1])) for (i++; isDigit(css[i]); i++);
      if ((css[i] === "e" || css[i] === "E") &&
          (isDigit(css[i + 1]) || ((css[i + 1] === "+" || css[i + 1] === "-") && isDigit(css[i + 2])))) {
        for (i += 2; isDigit(css[i]); i++);
      }
      value = "";
      if (startsIdent(i)) value = identSequence();
      else if (css[i] === "%") value = css[i++];
      type = "number";
    } else if (css.startsWith("-->", i) || css.startsWith("<!--", i)) {
      i += char === "-" ? 3 : 4;
      type = "html-comment";
    } else if (startsIdent(i)) {
      value = identSequence();
      type = "ident";
      if (css[i] === "(") {
        i++;
        type = "function";
        let next = i;
        while (isWhitespace(css[next])) next++;
        // Any spelling of url( without a quote is one token up to ")", so
        // comment, quote and bracket characters inside it are inert.
        if (asciiLower(value) === "url" && css[next] !== '"' && css[next] !== "'") {
          type = "url";
          value = "";
          for (i = next; i < css.length && css[i] !== ")"; ) {
            if (validEscape(i)) {
              value += escape();
              continue;
            }
            const code = css[i++];
            if (isWhitespace(code)) {
              while (isWhitespace(css[i])) i++;
              if (i < css.length && css[i] !== ")") type = "bad-url";
            } else if (code === '"' || code === "'" || code === "(" || code === "\\" || isNonPrintable(code)) {
              type = "bad-url";
            } else {
              value += code;
            }
          }
          i = Math.min(i + 1, css.length);
        }
      }
    } else {
      i++;
      if (!"()[]{},:;".includes(char)) type = "delim";
    }
    tokens.push({ type, value, start, end: i });
  }
  return tokens;
}

/** Index of the token that closes the block opened at tokens[open], or -1. */
function blockEnd(tokens, open) {
  const ends = [BLOCK_ENDS[tokens[open].type]];
  for (let k = open + 1; k < tokens.length; k++) {
    if (tokens[k].type === ends[ends.length - 1]) {
      ends.pop();
      if (!ends.length) return k;
    } else if (BLOCK_ENDS[tokens[k].type]) {
      ends.push(BLOCK_ENDS[tokens[k].type]);
    }
  }
  return -1;
}

/** Token indexes of the parenthesized root that begins an @scope prelude. */
function scopeRoot(tokens, from = 0) {
  let open = from;
  while (tokens[open] && tokens[open].type === "whitespace") open++;
  if (!tokens[open] || tokens[open].type !== "(") return null;
  const close = blockEnd(tokens, open);
  return close < 0 ? null : [open, close];
}

/** Indexes of the commas that separate a selector list, outside any block. */
function topLevelCommas(tokens) {
  const ends = [];
  const commas = [];
  tokens.forEach((token, index) => {
    if (token.type === ends[ends.length - 1]) ends.pop();
    else if (BLOCK_ENDS[token.type]) ends.push(BLOCK_ENDS[token.type]);
    else if (token.type === "," && !ends.length) commas.push(index);
  });
  return commas;
}

function splitSelectorList(selector) {
  const css = preprocessCSS(selector);
  const tokens = cssTokens(css);
  const pieces = [];
  let start = 0;
  for (const index of topLevelCommas(tokens)) {
    pieces.push(css.slice(start, tokens[index].start));
    start = tokens[index].end;
  }
  pieces.push(css.slice(start));
  return pieces;
}

function startsWithSiblingCombinator(selector) {
  const first = cssTokens(preprocessCSS(selector)).find((token) => token.type !== "whitespace");
  return first !== undefined && first.type === "delim" && (first.value === "+" || first.value === "~");
}

// Only literal identifiers/strings are resolved here; escaped and dynamic roots
// keep the existing fallback. Do not use jsdom.matches: its predicate semantics
// differ from browsers for missing attributes, whitespace and case folding.
const CSS_IDENTIFIER = String.raw`(?:--|-?[A-Za-z_\u0080-\uFFFF])[-\w\u0080-\uFFFF]*`;
const BODY_NAME = new RegExp(`^${CSS_IDENTIFIER}`);
const BODY_ATTRIBUTE = new RegExp(
  String.raw`^[\t\n\f\r ]*(${CSS_IDENTIFIER})[\t\n\f\r ]*(?:([~|^$*]?=)[\t\n\f\r ]*(?:"([^"\\\n\r\f]*)"|'([^'\\\n\r\f]*)'|(${CSS_IDENTIFIER}))([\t\n\f\r ]*)([isIS])?[\t\n\f\r ]*)?$`
);

// HTML defines these attribute values as ASCII-insensitive by default:
// https://html.spec.whatwg.org/multipage/semantics-other.html#case-sensitivity-of-selectors
const HTML_INSENSITIVE_ATTRIBUTES = new Set([
  "accept", "accept-charset", "align", "alink", "axis", "bgcolor", "charset",
  "checked", "clear", "codetype", "color", "compact", "declare", "defer", "dir",
  "direction", "disabled", "enctype", "face", "frame", "hreflang", "http-equiv",
  "lang", "language", "link", "media", "method", "multiple", "nohref", "noresize",
  "noshade", "nowrap", "readonly", "rel", "rev", "rules", "scope", "scrolling",
  "selected", "shape", "target", "text", "type", "valign", "valuetype", "vlink",
]);

function asciiLower(value) {
  return value.replace(/[A-Z]/g, (char) => char.toLowerCase());
}

function matchesBodyValue(actual, operator, expected, insensitive) {
  if (actual === null) return false;
  if (!operator) return true;
  if (insensitive) {
    actual = asciiLower(actual);
    expected = asciiLower(expected);
  }
  switch (operator) {
    case "=": return actual === expected;
    case "~=": return expected !== "" && actual.split(/[\t\n\f\r ]+/).includes(expected);
    case "|=": return actual === expected || actual.startsWith(expected + "-");
    case "^=": return expected !== "" && actual.startsWith(expected);
    case "$=": return expected !== "" && actual.endsWith(expected);
    case "*=": return expected !== "" && actual.includes(expected);
    default: return false;
  }
}

/** Resolve a static body compound without moving sender attributes into the app. */
function scopeQualifiedBodySelector(selector, body) {
  if (!body || !/^body[.#\[]/i.test(selector)) return null;
  const quirks = body.ownerDocument.compatMode === "BackCompat";
  let end = 4;
  while (end < selector.length) {
    const marker = selector[end];
    if (marker === "." || marker === "#") {
      const name = selector.slice(end + 1).match(BODY_NAME);
      if (!name) return null;
      const attribute = marker === "." ? "class" : "id";
      const operator = marker === "." ? "~=" : "=";
      if (!matchesBodyValue(body.getAttribute(attribute), operator, name[0], quirks)) return null;
      end += name[0].length + 1;
    } else if (marker === "[") {
      let quote = null;
      let close = end + 1;
      for (; close < selector.length; close++) {
        const char = selector[close];
        // Escaped roots are outside this deliberately bounded grammar.
        if (char === "\\") return null;
        if (quote) {
          if (char === quote) quote = null;
        } else if (char === '"' || char === "'") {
          quote = char;
        } else if (char === "]") {
          break;
        } else if (char === "[") {
          return null;
        }
      }
      if (close === selector.length) return null;
      const match = selector.slice(end + 1, close).match(BODY_ATTRIBUTE);
      if (!match) return null;
      const [, name, operator, doubleQuoted, singleQuoted, identifier, space, modifier] = match;
      if (identifier !== undefined && modifier && !space) return null;
      const flag = modifier && asciiLower(modifier);
      const insensitive = flag === "i" || (!flag && HTML_INSENSITIVE_ATTRIBUTES.has(asciiLower(name)));
      const value = doubleQuoted ?? singleQuoted ?? identifier;
      if (!matchesBodyValue(body.getAttribute(name), operator, value, insensitive)) return null;
      end = close + 1;
    } else {
      break;
    }
  }
  const suffix = selector.slice(end);
  if (suffix && !/^[\t\n\f\r >]/.test(suffix)) return null;
  // A sibling of the message container belongs to the app, not the message.
  if (startsWithSiblingCombinator(suffix)) return null;
  const compound = selector.slice(0, end);
  // The reader container is a DIV, so :not(body...) matches it while retaining
  // the original specificity. Unlike :is(), :not() does not forgive invalid CSS.
  return `#ownmail-email-content:not(${compound})${suffix}`;
}

/**
 * Confine one sender selector to the reader container. Naming the container
 * proves nothing: :not(), :has() or a sibling combinator can still leave it.
 * Returns null when the selector would select a sibling of the container.
 */
function scopeSelector(selector, body) {
  const sel = selector.trim();
  if (!sel) return sel;
  const qualified = scopeQualifiedBodySelector(sel, body);
  if (qualified) return qualified;
  // Replace standalone html/body with #ownmail-email-content
  if (/^(html|body)$/i.test(sel)) return "#ownmail-email-content";
  // Replace html/body prefix: "body .foo" → "#ownmail-email-content .foo"
  const root = sel.match(/^(html|body)\s+/i);
  if (root && !startsWithSiblingCombinator(sel.slice(root[0].length))) {
    return "#ownmail-email-content " + sel.slice(root[0].length);
  }
  // A leading + or ~ is invalid in a top-level rule and would otherwise
  // relate the container to its siblings.
  if (startsWithSiblingCombinator(sel)) return null;
  return "#ownmail-email-content " + sel;
}

/** Scope each selector of a list, or return null when any cannot be scoped. */
function scopeSelectorList(selectors, body) {
  const scoped = splitSelectorList(selectors).map((sel) => scopeSelector(sel, body));
  return scoped.includes(null) ? null : scoped;
}

/** Whether a selector can only match the container or its descendants. */
function isScopedSelector(tokens) {
  let k = 0;
  while (tokens[k] && tokens[k].type === "whitespace") k++;
  // An empty selector invalidates its whole rule.
  if (k === tokens.length) return true;
  if (tokens[k].type !== "hash" || tokens[k].value !== "ownmail-email-content") return false;
  const ends = [];
  for (k++; k < tokens.length; k++) {
    const { type, value } = tokens[k];
    if (type === ends[ends.length - 1]) ends.pop();
    else if (BLOCK_ENDS[type]) ends.push(BLOCK_ENDS[type]);
    else if (!ends.length && (type === "whitespace" || (type === "delim" && ">+~".includes(value)))) break;
  }
  while (tokens[k] && tokens[k].type === "whitespace") k++;
  return !(tokens[k] && tokens[k].type === "delim" && (tokens[k].value === "+" || tokens[k].value === "~"));
}

function isScopedSelectorList(tokens) {
  let start = 0;
  for (const index of [...topLevelCommas(tokens), tokens.length]) {
    if (!isScopedSelector(tokens.slice(start, index))) return false;
    start = index + 1;
  }
  return true;
}

/**
 * Read scoped output as a browser does and confirm that every style rule and
 * @scope root it finds is confined to the reader container.
 */
function isScopedStylesheet(tokens) {
  // Blocks whose contents are declarations and rules, or plain values.
  const blocks = [];
  let statement = 0;
  for (let k = 0; k < tokens.length; k++) {
    const { type } = tokens[k];
    const block = blocks[blocks.length - 1];
    if (block && type === block.end) {
      blocks.pop();
      if (block.statements) statement = k + 1;
      continue;
    }
    const statementLevel = !block || block.statements;
    // A top-level rule does not end at ";", but such a prelude is no selector.
    if (statementLevel && (type === ";" || type === "}")) {
      statement = k + 1;
    } else if (type === "{" && statementLevel) {
      let first = statement;
      // At the top level a browser skips HTML comment markers between rules.
      while (first < k && (tokens[first].type === "whitespace" ||
        (!block && tokens[first].type === "html-comment"))) first++;
      const prelude = tokens.slice(first, k);
      const head = prelude[0];
      const next = prelude.find((token, index) => index && token.type !== "whitespace");
      let entry = { end: "}", statements: true, keyframes: block && block.keyframes };
      if (head && head.type === "at-keyword") {
        const name = asciiLower(head.value);
        if (/^(-webkit-)?keyframes$/.test(name)) entry.keyframes = true;
        if (name === "scope") {
          const range = scopeRoot(prelude, 1);
          if (!range || !isScopedSelectorList(prelude.slice(range[0] + 1, range[1]))) return false;
        }
      } else if (head && head.type === "ident" && head.value.startsWith("--") && next && next.type === ":") {
        // A custom property value, not a rule.
        entry = { end: "}", statements: false };
      } else if (!entry.keyframes && !isScopedSelectorList(prelude)) {
        return false;
      }
      blocks.push(entry);
      statement = k + 1;
    } else if (BLOCK_ENDS[type]) {
      blocks.push({ end: BLOCK_ENDS[type], statements: false });
    }
  }
  return true;
}

/**
 * Whether the @import prelude that starts at tokens[from] loads from a trusted
 * font provider. A browser loads only its first component, a string or url();
 * a url() in a later layer(), supports() or media condition loads nothing.
 */
function isTrustedImport(css, tokens, from) {
  let k = from;
  const next = () => {
    while (tokens[k] && tokens[k].type === "whitespace") k++;
    return tokens[k++] || { type: "end" };
  };
  const first = next();
  let target = first;
  // url("...") is a function holding a string; it must close right after it.
  if (first.type === "function" && asciiLower(first.value) === "url") {
    target = next();
    if (next().type !== ")") return false;
  }
  if (target.type !== "string" && target.type !== "url") return false;
  // Speculative preload scanners read the raw text without decoding escapes.
  if (css.slice(first.start, tokens[k - 1].end).includes("\\")) return false;
  return isTrustedFontUrl(target.value);
}

/**
 * Confirm that every @import a browser finds in preprocessed output loads
 * from a trusted font provider. Chromium's preload scanner also requests
 * "@import" text that its CSS parser reads as part of a string or url(), so
 * that text may appear only where an @import rule starts.
 */
function hasOnlyTrustedImports(css, tokens) {
  const imports = new Set();
  for (const [k, token] of tokens.entries()) {
    if (token.type !== "at-keyword" || asciiLower(token.value) !== "import") continue;
    if (!isTrustedImport(css, tokens, k + 1)) return false;
    imports.add(token.start);
  }
  return Array.from(css.matchAll(/@import/gi)).every((match) => imports.has(match.index));
}

// Viewport units in a message resolve against the reader's frame, so they read
// the reader's viewport from custom properties and fall back to today's unit.
const VIEWPORT_UNITS = /^[sld]?v(?:(h|b)|(w|i)|(min)|(max))$/;

function rewriteViewportUnits(value) {
  const text = preprocessCSS(value);
  let result = "";
  let last = 0;
  for (const token of cssTokens(text)) {
    const unit = token.type === "number" && asciiLower(token.value).match(VIEWPORT_UNITS);
    if (!unit) continue;
    const source = text.slice(token.start, token.end);
    const number = source.match(/^[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?/)[0];
    const property = unit[1] ? "vh" : unit[2] ? "vw" : unit[3] ? "vmin" : "vmax";
    result += `${text.slice(last, token.start)}calc(${number} * var(--ownmail-${property}, 1${source.slice(number.length)}))`;
    last = token.end;
  }
  return last ? result + text.slice(last) : value;
}

/** Undo rewriteViewportUnits so padding detection sees the authored size. */
function restoreViewportUnits(value) {
  return value.replace(/calc\(([^ ]+) \* var\(--ownmail-v(?:h|w|min|max), 1([^)]+)\)\)/g, "$1$2");
}

/**
 * Scope and sanitize a CSS stylesheet using postcss AST.
 * - Removes @charset and escaped at-rule names; allows @import only from
 *   trusted font providers
 * - Removes dangerous CSS (expression(), behavior, -moz-binding, javascript:)
 * - Keeps remote url() values, including @font-face sources from any host; the
 *   reader's content security policy blocks them until remote content is loaded
 * - Scopes every selector and @scope root under #ownmail-email-content, and
 *   discards the stylesheet if a browser would read a rule outside that scope
 *   or an @import from another host, or could preload one
 * - Leaves @font-face, @keyframes and other global at-rules unscoped
 */
function scopeAndSanitizeCSS(css, body = null) {
  let root;
  try {
    // Ignore sourceMappingURL comments so message CSS cannot make postcss read local files.
    root = postcss.parse(prepareStyleText(css), { map: false });
  } catch (e) {
    return "/* CSS parse error */";
  }

  // Remove @import and @charset (allow @import from trusted font providers)
  root.walkAtRules((atRule) => {
    const name = atRule.name.toLowerCase();
    // postcss ends a name at a backslash, but browsers decode the escape and
    // read on, so "@imp\6f rt" is an @import. Drop it rather than guess.
    const escapedName = !atRule.raws.afterName && atRule.params.startsWith("\\");
    if (escapedName || name === "charset") {
      atRule.remove();
    } else if (name === "import") {
      // Read the prelude as printed; postcss drops some comments from params.
      const prelude = preprocessCSS(atRule.raws.params ? atRule.raws.params.raw : atRule.params);
      if (!isTrustedImport(prelude, cssTokens(prelude), 0)) atRule.remove();
    }
  });
  // A commented-out @import would otherwise discard the stylesheet below.
  root.walkComments((comment) => {
    if (/@import/i.test(comment.text)) comment.remove();
  });

  // Sanitize declarations
  root.walkDecls((decl) => {
    const prop = decl.prop.toLowerCase();
    const val = decl.value;

    // Remove dangerous properties
    if (prop === "behavior" || prop === "-moz-binding") {
      decl.remove();
      return;
    }

    // Remove dangerous values
    if (/expression\s*\(/i.test(val) || /javascript\s*:/i.test(val)) {
      decl.remove();
      return;
    }

    // Remote url() values stay for the reader's content security policy to
    // block. Only javascript: URLs are a security risk.
    if (/url\s*\(\s*['"]?javascript:/i.test(val)) {
      decl.remove();
      return;
    }

    // A font-face family descriptor names one font, not a fallback list.
    const fontFace = decl.parent.type === "atrule" && decl.parent.name.toLowerCase() === "font-face";
    if (!fontFace && (prop === "font-family" || prop === "font")) {
      decl.value = ensureFontFallback(decl.value);
    }
    decl.value = rewriteViewportUnits(decl.value);
  });

  // Scope selectors under #ownmail-email-content
  root.walkRules((rule) => {
    // Don't scope rules inside @keyframes
    if (
      rule.parent &&
      rule.parent.type === "atrule" &&
      /^(-webkit-)?keyframes$/i.test(rule.parent.name)
    ) {
      return;
    }

    const selectors = scopeSelectorList(rule.selector, body);
    if (selectors) rule.selectors = selectors;
    else rule.remove();
  });

  // Declarations directly inside @scope style its root, so the root is scoped
  // like any selector. A missing root becomes the reader container explicitly.
  root.walkAtRules(/^scope$/i, (atRule) => {
    const params = preprocessCSS(atRule.params);
    const tokens = cssTokens(params);
    const first = tokens.find((token) => token.type !== "whitespace");
    if (!first || (first.type === "ident" && asciiLower(first.value) === "to")) {
      atRule.params = `(#ownmail-email-content) ${params.trim()}`.trim();
      atRule.raws.afterName = " ";
      return;
    }
    const range = scopeRoot(tokens);
    const roots = range && scopeSelectorList(params.slice(tokens[range[0]].end, tokens[range[1]].start), body);
    if (roots) atRule.params = `(${roots.join(", ")})${params.slice(tokens[range[1]].end)}`;
    else atRule.remove();
  });

  // postcss may still have read an @import or a rule differently from browsers.
  const scoped = root.toString();
  const text = preprocessCSS(scoped);
  const tokens = cssTokens(text);
  return isScopedStylesheet(tokens) && hasOnlyTrustedImports(text, tokens) ? scoped : "/* CSS parse error */";
}

/**
 * Sanitize inline style attribute values.
 * Removes dangerous CSS constructs but does NOT scope (no selectors in inline styles).
 */
function sanitizeInlineStyle(css) {
  // Remove javascript: URLs (security risk). Remote URLs stay for the reader's
  // content security policy to block.
  css = css.replace(/url\s*\(\s*['"]?javascript:[^)]*\)/gi, "/* url removed */");
  css = css.replace(/expression\s*\([^)]*\)/gi, "");
  css = css.replace(/behavior\s*:\s*[^;]*/gi, "");
  css = css.replace(/-moz-binding\s*:\s*[^;]*/gi, "");
  css = css.replace(/javascript\s*:/gi, "");

  // Ensure font-family in inline styles ends with a generic fallback
  css = css.replace(
    /font-family\s*:\s*([^;]+)/gi,
    (match, value) => "font-family: " + ensureFontFallback(value.trim())
  );

  return rewriteViewportUnits(css);
}

// Head styles arrive before BODY attributes are sanitized. Keep their source
// so later resolution does not reinterpret sender-authored already-scoped CSS.
const pendingBodyStyles = new WeakMap();
const sanitizedBodies = new WeakSet();

// Hook into DOMPurify to sanitize and scope CSS, and filter <link> tags
purify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName === "style" && node.textContent) {
    const body = node.ownerDocument.body;
    const context = sanitizedBodies.has(body) ? body : null;
    if (!context) pendingBodyStyles.set(node, node.textContent);
    node.textContent = scopeAndSanitizeCSS(node.textContent, context);
  }

  // Allow <link rel="stylesheet"> only from trusted font providers
  if (data.tagName === "link") {
    const rel = (node.getAttribute && node.getAttribute("rel") || "").toLowerCase();
    const href = node.getAttribute && node.getAttribute("href") || "";
    if (rel === "stylesheet" && isTrustedFontUrl(href)) {
      return; // keep it
    }
    // Remove all other <link> tags
    node.parentNode && node.parentNode.removeChild(node);
  }
});

purify.addHook("afterSanitizeAttributes", (node) => {
  // Sanitize inline style attributes
  if (node.hasAttribute && node.hasAttribute("style")) {
    const style = node.getAttribute("style");
    node.setAttribute("style", sanitizeInlineStyle(style));
  }

  if (node.tagName === "BODY") {
    // Body predicates must see the final inline CSS, including removed unsafe
    // values and added font fallbacks, just like styles encountered in the body.
    sanitizedBodies.add(node);
    for (const style of node.ownerDocument.querySelectorAll("style")) {
      const original = pendingBodyStyles.get(style);
      if (original === undefined) continue;
      style.textContent = scopeAndSanitizeCSS(original, node);
      pendingBodyStyles.delete(style);
    }
  }

  // Links, including image-map areas, open in a new tab without a referrer
  if (node.tagName === "A" || node.tagName === "AREA") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

/**
 * Whether a parsed @media condition tests prefers-color-scheme: dark. Text in
 * CSS strings and comments, inside or outside the condition, does not count.
 */
function hasDarkModeMedia(css) {
  let found = false;
  postcss.parse(css, { map: false }).walkAtRules(/^media$/i, (atRule) => {
    const tokenizer = tokenizeCSS(new postcss.Input(atRule.params, { map: false }));
    let condition = "";
    while (!tokenizer.endOfFile()) {
      const token = tokenizer.nextToken();
      condition += token[0] === "string" || token[0] === "comment" ? " " : token[1];
    }
    if (/\(\s*prefers-color-scheme\s*:\s*dark\s*\)/i.test(condition)) found = true;
  });
  return found;
}

/**
 * Detect whether an email supports dark mode natively.
 *
 * Returns true if:
 * 1. The email's CSS contains @media (prefers-color-scheme: dark), OR
 * 2. The email's first content elements use dark backgrounds (luminance < 0.4)
 *
 * When true, we let the email render naturally in dark mode.
 * When false, we force a light background so text remains readable.
 */
function detectSupportsDarkMode(html) {
  try {
    const dom = new JSDOM(html);
    const doc = dom.window.document;

    // Check for dark mode media queries in <style> blocks
    const styles = doc.querySelectorAll("style");
    for (const style of styles) {
      if (hasDarkModeMedia(style.textContent)) return true;
    }

    // Check if the email uses dark backgrounds explicitly
    const body = doc.body;
    if (!body) return false;

    const children = Array.from(body.children);
    const contentElements = children.filter(
      (el) => el.tagName.toLowerCase() !== "style"
    );

    for (const el of contentElements.slice(0, 2)) {
      if (isDarkBackground(el)) return true;
      const firstChild = el.children[0];
      if (firstChild && isDarkBackground(firstChild)) return true;
    }

    return false;
  } catch (e) {
    return false; // Default to forced light mode on error
  }
}

/**
 * Check if an element has a dark background color.
 */
function isDarkBackground(el) {
  let color = el.getAttribute("bgcolor");
  if (color) return isColorDark(color);

  const style = el.getAttribute("style") || "";
  const match = style.match(/background(?:-color)?\s*:\s*([^;]+)/i);
  if (match) return isColorDark(match[1].trim());

  return false;
}

/**
 * Determine if a color string is dark (luminance < 0.4).
 * Supports hex (#rgb, #rrggbb), rgb(), and named colors.
 */
function isColorDark(color) {
  color = color.trim().toLowerCase();

  // Named colors (common dark ones)
  const darkNames = new Set([
    "black", "darkblue", "darkgreen", "darkred", "darkgray", "darkgrey",
    "darkslategray", "darkslategrey", "darkviolet", "darkcyan", "darkmagenta",
    "darkolivegreen", "darkslateblue", "midnightblue", "navy", "maroon",
    "indigo", "darkkhaki", "dimgray", "dimgrey",
  ]);
  if (darkNames.has(color)) return true;

  let r, g, b;

  // Hex
  const hexMatch = color.match(/^#([0-9a-f]{3,8})$/);
  if (hexMatch) {
    const hex = hexMatch[1];
    if (hex.length === 3) {
      r = parseInt(hex[0] + hex[0], 16);
      g = parseInt(hex[1] + hex[1], 16);
      b = parseInt(hex[2] + hex[2], 16);
    } else if (hex.length >= 6) {
      r = parseInt(hex.slice(0, 2), 16);
      g = parseInt(hex.slice(2, 4), 16);
      b = parseInt(hex.slice(4, 6), 16);
    } else {
      return false;
    }
  }

  // rgb() / rgba()
  if (r === undefined) {
    const rgbMatch = color.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (rgbMatch) {
      r = parseInt(rgbMatch[1]);
      g = parseInt(rgbMatch[2]);
      b = parseInt(rgbMatch[3]);
    }
  }

  if (r === undefined) return false;

  // Relative luminance (simplified sRGB)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance < 0.4;
}

// Padding detection proves only simple, unconditional layout facts. It does
// not simulate the CSS cascade (jsdom does not implement its specificity).
function paddingSelector(selector) {
  const parts = selector.trim().split(/([\t\n\f\r ]*>[\t\n\f\r ]*|[\t\n\f\r ]+)/);
  const compound = new RegExp(`^(?:${CSS_IDENTIFIER}|\\*)?(?:[.#]${CSS_IDENTIFIER})*$`);
  const qualifier = new RegExp(`([.#])(${CSS_IDENTIFIER})`, "g");
  if (parts[0] !== "#ownmail-email-content" || parts.length % 2 !== 1) return null;
  const selectors = [];
  for (let i = 0; i < parts.length; i += 2) {
    if (!parts[i] || !compound.test(parts[i])) return null;
    const tag = parts[i].match(BODY_NAME)?.[0];
    const qualifiers = Array.from(parts[i].matchAll(qualifier));
    selectors.push({ tag, qualifiers, child: i > 0 && parts[i - 1].includes(">") });
  }
  const cache = new WeakMap();
  function matches(element, index) {
    if (!element) return false;
    if (!cache.has(element)) cache.set(element, new Map());
    const results = cache.get(element);
    if (!results.has(index)) results.set(index, evaluate(element, index));
    return results.get(index);
  }
  function evaluate(element, index) {
    const { tag, qualifiers, child } = selectors[index];
    if (tag && asciiLower(element.tagName) !== asciiLower(tag)) return false;
    for (const [, marker, name] of qualifiers) {
      if (!matchesBodyValue(element.getAttribute(marker === "." ? "class" : "id"),
        marker === "." ? "~=" : "=", name, false)) return false;
    }
    if (!index) return true;
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (matches(parent, index - 1)) return true;
      if (child) break;
    }
    return false;
  }
  return (element) => matches(element, selectors.length - 1);
}

function paddingStyles(doc, container) {
  const elements = [container, ...container.querySelectorAll("*")];
  const styles = new Map(elements.map((element) => [element, new Map()]));
  const relevant = /^(?:background(?:-.*)?|(?:-webkit-)?(?:background-clip|mask(?:-.*)?)|display|visibility|content-visibility|opacity|position|float|(?:(?:min|max)-)?(?:width|height|inline-size|block-size)|font|font-size|line-height|overflow(?:-[xy])?|clip(?:-path)?|transform|filter|content|all|animation(?:-.*)?|transition(?:-.*)?)$/;
  const probe = doc.createElement("div").style;
  function remember(element, property, value) {
    const properties = styles.get(element);
    if (!properties.has(property)) properties.set(property, new Set());
    properties.get(property).add(value);
  }
  function declarations(nodes, targets) {
    for (const decl of nodes) {
      if (decl.type === "comment") continue;
      if (decl.type !== "decl") return false;
      if (decl.prop.includes("\\")) return false;
      const property = decl.prop.toLowerCase();
      if (!relevant.test(property)) continue;
      probe.cssText = "";
      probe.setProperty(property, restoreViewportUnits(decl.value));
      const value = asciiLower(probe.getPropertyValue(property));
      if (!value || /\b(?:var|env)\s*\(|\b(?:inherit|initial|unset|revert|revert-layer|currentcolor)\b/i.test(value)) return false;
      for (const element of targets) {
        if (property === "background") {
          remember(element, "background-color", asciiLower(probe.backgroundColor) || "transparent");
          remember(element, "background-image", probe.backgroundImage || "none");
          remember(element, "background-clip", probe.backgroundClip || "border-box");
        } else if (property === "font") {
          remember(element, "font-size", probe.fontSize);
          remember(element, "line-height", probe.lineHeight || "normal");
        } else {
          remember(element, property, value);
        }
      }
    }
    return true;
  }
  for (const style of doc.querySelectorAll("style")) {
    if ((style.getAttribute("type") || "text/css").trim().toLowerCase() !== "text/css") continue;
    const css = postcss.parse(style.textContent, { map: false });
    let uncertain = false;
    css.walkRules((rule) => {
      if (!rule.nodes.some((node) => node.type === "decl" &&
        (relevant.test(node.prop.toLowerCase()) || node.prop.includes("\\")))) return;
      const selectors = rule.selectors.map(paddingSelector);
      if (selectors.some((selector) => !selector)) { uncertain = true; return; }
      const targets = elements.filter((element) => selectors.some((selector) => selector(element)));
      if (!targets.length) return;
      if (rule.parent.type !== "root" || (style.getAttribute("media") || "all").toLowerCase() !== "all") {
        uncertain = true;
        return;
      }
      if (!declarations(rule.nodes, targets)) uncertain = true;
    });
    if (uncertain) return null;
  }
  for (const element of elements) {
    if (/^(TABLE|TD|TH|TR|THEAD|TBODY|TFOOT)$/.test(element.tagName) && element.hasAttribute("bgcolor")) {
      probe.cssText = "";
      probe.backgroundColor = element.getAttribute("bgcolor");
      if (!probe.backgroundColor) return null;
      remember(element, "background-color", asciiLower(probe.backgroundColor));
    }
    const inline = element.getAttribute("style");
    if (inline && !declarations(postcss.parse(inline, { map: false }).nodes, [element])) return null;
  }
  return new Map(Array.from(styles, ([element, properties]) => [element,
    Object.fromEntries(Array.from(properties, ([name, values]) => [name, values.size === 1 ? [...values][0] : "?"]))]));
}

/** Recognize a visible authored canvas without altering the sanitized message. */
function detectNeedsPadding(html) {
  let dom;
  try {
    // Match the standards-mode reader DIV, not the discarded sender BODY.
    // No resources or scripts are loaded in this disposable document.
    dom = new JSDOM("<!doctype html>" + html);
    const doc = dom.window.document;
    const container = doc.createElement("div");
    container.id = "ownmail-email-content";
    container.className = "ownmail-email-content-html";
    if (doc.body.hasAttribute("style")) container.setAttribute("style", doc.body.getAttribute("style"));
    container.append(...doc.body.childNodes);
    doc.body.replaceChildren(container);
    for (const attribute of Array.from(doc.body.attributes)) doc.body.removeAttribute(attribute.name);
    const styles = paddingStyles(doc, container);
    if (!styles) return true;

    const copy = [];
    const images = [];
    const visible = new Set();
    let uncertain = false;
    function visit(element, inheritedVisibility = "visible") {
      if (/^(STYLE|LINK|TEMPLATE|HR|BR)$/.test(element.tagName)) return;
      const style = styles.get(element);
      if (style.display === "none" || style.opacity === "0" || (element.hidden && !style.display)) return;
      if (Object.values(style).includes("?") ||
          (/^(DETAILS|DIALOG)$/.test(element.tagName) && !element.hasAttribute("open")) ||
          (style.opacity && style.opacity !== "1") ||
          (style["content-visibility"] && style["content-visibility"] !== "visible") ||
          (style.position && !/^(static|relative)$/.test(style.position)) ||
          (style.float && style.float !== "none") ||
          Object.keys(style).some((name) => /^(all|animation|transition|clip|transform|filter|content$|mask|-webkit-)/.test(name)) ||
          Object.entries(style).some(([name, value]) => /(?:width|height|size|line-height)$/.test(name) &&
            (/^0(?:[a-z%]*)$/i.test(value) || value.includes("(")))) {
        uncertain = true;
        return;
      }
      const visibility = style.visibility || inheritedVisibility;
      if (visibility === "visible") visible.add(element);
      if (element.tagName === "IMG") {
        if (visibility === "visible") images.push(element);
        return;
      }
      for (const node of element.childNodes) {
        if (node.nodeType === 3 && /\S/.test(node.textContent) && visibility === "visible") copy.push(node);
        else if (node.nodeType === 1) visit(node, visibility);
      }
    }
    visit(container);
    if (uncertain || !copy.length) return true;
    for (let element = copy[0].parentElement; element && container.contains(element); element = element.parentElement) {
      if (!visible.has(element) || !/^(DIV|SECTION|ARTICLE|MAIN|TABLE|TD|TH)$/.test(element.tagName)) continue;
      const style = styles.get(element);
      if (style.display && !/^(block|table|table-cell)$/.test(style.display)) continue;
      if (!copy.every((node) => element.contains(node))) continue;
      // A caption cannot stand in for another image-bearing layout region.
      // Direct trailing inline images retain the existing reader behavior.
      if (images.some((image) => !element.contains(image) &&
        (image.parentElement !== container ||
          (styles.get(image).display && !/^(inline|inline-block)$/.test(styles.get(image).display)) ||
          !(element.compareDocumentPosition(image) & 4)))) continue;
      // A colored cell beside another cell is not proof of a full canvas.
      let competingCell = false;
      for (let parent = element; parent !== container; parent = parent.parentElement) {
        if (/^(TD|TH)$/.test(parent.tagName) && parent.parentElement.children.length !== 1) competingCell = true;
      }
      if (competingCell) continue;
      const color = style["background-color"];
      if (!color || color === "transparent" || !/^(?:[a-z]+|rgb\([\d\s,.]+\))$/i.test(color)) continue;
      if (style["background-image"] && style["background-image"] !== "none") continue;
      if (style["background-clip"] && style["background-clip"] !== "border-box") continue;
      return false;
    }
    return true;
  } catch (e) {
    return true;
  } finally {
    if (dom) dom.window.close();
  }
}

// Process input line by line
const readline = require("readline");
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
});

rl.on("line", (line) => {
  let request;
  try {
    request = JSON.parse(line);
  } catch (e) {
    // Invalid JSON - write error and continue
    process.stdout.write(
      JSON.stringify({ id: null, html: "", error: "Invalid JSON input" }) + "\n"
    );
    return;
  }

  const { id, html } = request;

  try {
    const clean = purify.sanitize(html, PURIFY_CONFIG);

    // Preserve an identifiable sender canvas; keep readable reader padding
    // for simple HTML and layouts whose background/visibility is uncertain.
    const needsPadding = detectNeedsPadding(clean);

    // Detect if the email supports dark mode natively (has dark-mode CSS
    // or uses dark backgrounds).  If so, we skip forcing a light background.
    const supportsDarkMode = detectSupportsDarkMode(clean);

    process.stdout.write(JSON.stringify({ id, html: clean, error: null, needsPadding, supportsDarkMode }) + "\n");
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ id, html: html, error: e.message }) + "\n"
    );
  }
});

rl.on("close", () => {
  process.exit(0);
});

// Signal ready
process.stdout.write(JSON.stringify({ id: 0, html: "", error: null, ready: true }) + "\n");
