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
    // "link" is NOT forbidden — we filter it in the uponSanitizeElement hook
  ],

  // Allow safe attributes
  FORBID_ATTR: [
    // Event handlers are blocked by DOMPurify by default,
    // but explicitly forbid dangerous attributes
    "formaction", "xlink:href", "xmlns",
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
    // Extract URL from url() or @import url() or @import "..."
    const match = url.match(/url\s*\(\s*['"]?([^'")\s]+)/i) || url.match(/['"]([^'"]+)['"]/);
    if (!match) return false;
    const parsed = new URL(match[1]);
    return TRUSTED_FONT_HOSTS.includes(parsed.hostname);
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
  const relationship = suffix.replace(/^(?:[\t\n\f\r ]|\/\*[\s\S]*?\*\/)*/, "");
  // A sibling of the message container belongs to the app, not the message.
  if (/^[+~]/.test(relationship)) return null;
  const compound = selector.slice(0, end);
  // The reader container is a DIV, so :not(body...) matches it while retaining
  // the original specificity. Unlike :is(), :not() does not forgive invalid CSS.
  return `#ownmail-email-content:not(${compound})${suffix}`;
}

/**
 * Scope and sanitize a CSS stylesheet using postcss AST.
 * - Removes @charset; allows @import only from trusted font providers
 * - Removes dangerous CSS (expression(), behavior, -moz-binding, javascript:)
 * - Keeps remote url() values, including @font-face sources from any host; the
 *   reader's content security policy blocks them until remote content is loaded
 * - Scopes all selectors under #ownmail-email-content
 * - Leaves @font-face, @keyframes unscoped
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
    if (name === "charset") {
      atRule.remove();
    } else if (name === "import") {
      if (!isTrustedFontUrl(atRule.params)) {
        atRule.remove();
      }
    }
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

    rule.selectors = rule.selectors.map((sel) => {
      sel = sel.trim();
      if (!sel) return sel;
      // Already scoped
      if (sel.includes("#ownmail-email-content")) return sel;
      const qualified = scopeQualifiedBodySelector(sel, body);
      if (qualified) return qualified;
      // Replace standalone html/body with #ownmail-email-content
      if (/^(html|body)$/i.test(sel)) return "#ownmail-email-content";
      // Replace html/body prefix: "body .foo" → "#ownmail-email-content .foo"
      if (/^(html|body)\s/i.test(sel)) {
        return sel.replace(/^(html|body)\s+/i, "#ownmail-email-content ");
      }
      // Prefix everything else
      return "#ownmail-email-content " + sel;
    });
  });

  return root.toString();
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

  return css;
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
    if (rel === "stylesheet" && href) {
      try {
        const parsed = new URL(href);
        if (TRUSTED_FONT_HOSTS.includes(parsed.hostname)) {
          return; // keep it
        }
      } catch {}
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

  // Force links and forms to open in new tab
  if (node.tagName === "A" || node.tagName === "FORM") {
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
      probe.setProperty(property, decl.value);
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
