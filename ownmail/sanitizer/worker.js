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
 * Scope and sanitize a CSS stylesheet using postcss AST.
 * - Removes @import, @charset
 * - Removes @media (prefers-color-scheme: dark) blocks
 * - Removes dangerous CSS (expression(), behavior, -moz-binding, javascript:)
 * - Removes url() with external resources (keeps data: URIs)
 * - Scopes all selectors under #email-content
 * - Leaves @font-face, @keyframes unscoped
 */
function scopeAndSanitizeCSS(css) {
  let root;
  try {
    root = postcss.parse(css);
  } catch (e) {
    return "/* CSS parse error */";
  }

  // Remove @import and @charset
  root.walkAtRules((atRule) => {
    const name = atRule.name.toLowerCase();
    if (name === "import" || name === "charset") {
      atRule.remove();
    }
  });

  // Remove dark mode media queries
  root.walkAtRules("media", (atRule) => {
    if (/prefers-color-scheme\s*:\s*dark/i.test(atRule.params)) {
      atRule.remove();
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

    // Remove url() with external resources, keep data: URIs
    if (/url\s*\(/i.test(val) && !/url\s*\(\s*['"]?data:/i.test(val)) {
      decl.remove();
    }
  });

  // Scope selectors under #email-content
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
      if (sel.includes("#email-content")) return sel;
      // Replace standalone html/body with #email-content
      if (/^(html|body)$/i.test(sel)) return "#email-content";
      // Replace html/body prefix: "body .foo" → "#email-content .foo"
      if (/^(html|body)\s/i.test(sel)) {
        return sel.replace(/^(html|body)\s+/i, "#email-content ");
      }
      // Prefix everything else
      return "#email-content " + sel;
    });
  });

  return root.toString();
}

/**
 * Sanitize inline style attribute values.
 * Removes dangerous CSS constructs but does NOT scope (no selectors in inline styles).
 */
function sanitizeInlineStyle(css) {
  css = css.replace(
    /url\s*\(\s*(?!['"]?data:)['"]?[^)]*['"]?\s*\)/gi,
    "/* url removed */"
  );
  css = css.replace(/expression\s*\([^)]*\)/gi, "");
  css = css.replace(/behavior\s*:\s*[^;]*/gi, "");
  css = css.replace(/-moz-binding\s*:\s*[^;]*/gi, "");
  css = css.replace(/javascript\s*:/gi, "");
  return css;
}

// Hook into DOMPurify to sanitize and scope CSS
purify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName === "style" && node.textContent) {
    node.textContent = scopeAndSanitizeCSS(node.textContent);
  }
});

purify.addHook("afterSanitizeAttributes", (node) => {
  // Sanitize inline style attributes
  if (node.hasAttribute && node.hasAttribute("style")) {
    const style = node.getAttribute("style");
    node.setAttribute("style", sanitizeInlineStyle(style));
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
