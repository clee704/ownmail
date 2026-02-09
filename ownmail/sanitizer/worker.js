#!/usr/bin/env node
"use strict";

/**
 * DOMPurify sanitization worker for ownmail.
 *
 * Long-lived process that reads newline-delimited JSON from stdin,
 * sanitizes HTML using DOMPurify + jsdom, and writes results to stdout.
 *
 * Protocol:
 *   Request:  {"id": 1, "html": "<div>...</div>"}
 *   Response: {"id": 1, "html": "<div>...</div>", "error": null}
 */

const { JSDOM } = require("jsdom");
const DOMPurify = require("dompurify");

// Create a single jsdom window and DOMPurify instance (reused across requests)
const window = new JSDOM("").window;
const purify = DOMPurify(window);

// DOMPurify configuration
const PURIFY_CONFIG = {
  // Explicitly forbid dangerous elements
  FORBID_TAGS: [
    "script", "iframe", "object", "embed", "form", "input", "button",
    "select", "textarea", "applet", "meta", "link", "base",
    "math", "svg", "noscript",
  ],

  // Allow safe attributes
  FORBID_ATTR: [
    // Event handlers are blocked by DOMPurify by default,
    // but explicitly forbid dangerous attributes
    "action", "formaction", "xlink:href", "xmlns",
  ],

  // Allow data: URIs for inline images (CID replacements)
  ALLOW_DATA_ATTR: true,
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|data):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,

  // Keep the full document structure so we can extract body content later
  WHOLE_DOCUMENT: true,
  // Return string, not DOM node
  RETURN_DOM: false,
  RETURN_DOM_FRAGMENT: false,
};

/**
 * Remove @media blocks targeting dark mode (prefers-color-scheme: dark).
 * We force email content to render in light mode, so dark mode CSS is harmful.
 * Uses brace counting to handle nested rules.
 */
function removeDarkModeBlocks(css) {
  const re = /@media\b/gi;
  let result = "";
  let lastIndex = 0;
  let match;

  while ((match = re.exec(css)) !== null) {
    const bracePos = css.indexOf("{", match.index);
    if (bracePos === -1) break;

    const prelude = css.substring(match.index, bracePos);
    if (/prefers-color-scheme\s*:\s*dark/i.test(prelude)) {
      result += css.substring(lastIndex, match.index);
      // Count braces to find the end of this block
      let depth = 1;
      let i = bracePos + 1;
      while (i < css.length && depth > 0) {
        if (css[i] === "{") depth++;
        else if (css[i] === "}") depth--;
        i++;
      }
      lastIndex = i;
      re.lastIndex = i;
    }
  }

  result += css.substring(lastIndex);
  return result;
}

/**
 * Split CSS into top-level chunks using brace counting.
 * Returns array of { type, raw, prelude, body } objects.
 * Types: 'rule' (regular rules), 'font-face', 'keyframes', 'media', 'at-rule'
 */
function splitTopLevel(css) {
  const chunks = [];
  let i = 0;
  const len = css.length;

  while (i < len) {
    // Skip whitespace
    while (i < len && /\s/.test(css[i])) i++;
    if (i >= len) break;

    if (css[i] === "@") {
      // At-rule
      const nameMatch = css.substring(i).match(/^@([\w-]+)/);
      if (!nameMatch) { i++; continue; }

      const name = nameMatch[1].toLowerCase();
      const bracePos = css.indexOf("{", i);
      const semiPos = css.indexOf(";", i);

      // Statement at-rule (no block) — @import, @charset, etc.
      if (bracePos === -1 || (semiPos !== -1 && semiPos < bracePos)) {
        const end = semiPos !== -1 ? semiPos + 1 : len;
        chunks.push({ type: "at-rule", raw: css.substring(i, end) });
        i = end;
        continue;
      }

      // Block at-rule — find matching closing brace
      let depth = 1;
      let j = bracePos + 1;
      while (j < len && depth > 0) {
        if (css[j] === "{") depth++;
        else if (css[j] === "}") depth--;
        j++;
      }

      const raw = css.substring(i, j);
      const prelude = css.substring(i, bracePos);
      const body = css.substring(bracePos + 1, j - 1);

      if (name === "font-face") {
        chunks.push({ type: "font-face", raw });
      } else if (name === "keyframes" || name === "-webkit-keyframes") {
        chunks.push({ type: "keyframes", raw });
      } else if (name === "media") {
        chunks.push({ type: "media", raw, prelude, body });
      } else {
        chunks.push({ type: "at-rule", raw });
      }
      i = j;
    } else {
      // Regular CSS rules — collect until next top-level at-rule or end
      const start = i;
      while (i < len) {
        if (css[i] === "@") break;
        if (css[i] === "{") {
          let depth = 1;
          i++;
          while (i < len && depth > 0) {
            if (css[i] === "{") depth++;
            else if (css[i] === "}") depth--;
            i++;
          }
        } else {
          i++;
        }
      }
      const raw = css.substring(start, i);
      if (raw.trim()) {
        chunks.push({ type: "rule", raw });
      }
    }
  }

  return chunks;
}

/**
 * Scope CSS selectors under #email-content to prevent email styles
 * from leaking into the host page. Uses brace-counting parser to
 * properly handle nested @media, @font-face, and @keyframes blocks.
 */
function scopeCSS(css) {
  // Strip dark mode media queries (we force light mode for email content)
  css = removeDarkModeBlocks(css);

  const chunks = splitTopLevel(css);

  return chunks.map((chunk) => {
    switch (chunk.type) {
      case "font-face":
      case "keyframes":
      case "at-rule":
        // Don't scope these
        return chunk.raw;
      case "media":
        // Scope the rules inside @media
        return chunk.prelude + "{" + scopeRules(chunk.body) + "}";
      case "rule":
        // Scope regular rules
        return scopeRules(chunk.raw);
      default:
        return chunk.raw;
    }
  }).join("\n");
}

/**
 * Scope individual CSS rules by prefixing selectors with #email-content.
 */
function scopeRules(css) {
  return css.replace(
    /([^{}@/][^{}]*?)\s*\{/g,
    (match, selectorGroup) => {
      // Skip if it looks like a comment or already scoped
      if (selectorGroup.trim().startsWith("/*") || selectorGroup.includes("#email-content")) {
        return match;
      }
      const scoped = selectorGroup
        .split(",")
        .map((sel) => {
          sel = sel.trim();
          if (!sel) return sel;
          // Replace html/body selectors with #email-content
          if (/^(html|body)$/i.test(sel)) {
            return "#email-content";
          }
          // Replace html/body prefix: "body .foo" → "#email-content .foo"
          sel = sel.replace(/^(html|body)\s+/i, "#email-content ");
          // If not already scoped, prefix
          if (!sel.startsWith("#email-content")) {
            sel = "#email-content " + sel;
          }
          return sel;
        })
        .join(", ");
      return scoped + " {";
    }
  );
}

/**
 * Hook: sanitize CSS in style attributes and <style> tags.
 * Removes dangerous CSS constructs:
 * - @import rules (external resource loading)
 * - url() references to external resources (keep data: URIs)
 * - expression() (IE JS execution)
 * - behavior: (IE HTC)
 * - -moz-binding: (Firefox XBL)
 * - javascript: in any property
 */
function sanitizeCSS(css) {
  // Remove @import rules
  css = css.replace(/@import\b[^;]*;?/gi, "/* @import removed */");

  // Remove url() with external resources, but keep data: URIs
  css = css.replace(
    /url\s*\(\s*(?!['"]?data:)['"]?[^)]*['"]?\s*\)/gi,
    "/* url removed */"
  );

  // Remove expression() (IE)
  css = css.replace(/expression\s*\([^)]*\)/gi, "/* expression removed */");

  // Remove behavior: (IE HTC files)
  css = css.replace(/behavior\s*:\s*[^;]*/gi, "/* behavior removed */");

  // Remove -moz-binding: (Firefox XBL)
  css = css.replace(/-moz-binding\s*:\s*[^;]*/gi, "/* -moz-binding removed */");

  // Remove javascript: in any value
  css = css.replace(/javascript\s*:/gi, "/* javascript removed */");

  return css;
}

// Hook into DOMPurify to sanitize and scope CSS
purify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName === "style" && node.textContent) {
    let css = sanitizeCSS(node.textContent);
    css = scopeCSS(css);
    node.textContent = css;
  }
});

purify.addHook("afterSanitizeAttributes", (node) => {
  // Sanitize inline style attributes
  if (node.hasAttribute && node.hasAttribute("style")) {
    const style = node.getAttribute("style");
    node.setAttribute("style", sanitizeCSS(style));
  }

  // Force links to open in new tab and add noopener
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

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
    process.stdout.write(JSON.stringify({ id, html: clean, error: null }) + "\n");
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
