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
    "script", "iframe", "object", "embed",
    "applet", "meta", "link", "base",
    "math", "svg", "noscript",
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

  // Keep the full document structure so we can extract body content later
  WHOLE_DOCUMENT: true,
  // Return string, not DOM node
  RETURN_DOM: false,
  RETURN_DOM_FRAGMENT: false,
};

// Trusted font provider domains (for @import and @font-face url())
const TRUSTED_FONT_HOSTS = [
  "fonts.googleapis.com",
  "fonts.gstatic.com",
  "use.typekit.net",    // Adobe Fonts
  "p.typekit.net",
  "fast.fonts.net",     // Monotype
  "cloud.typography.com", // Hoefler
];

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
 * Scope and sanitize a CSS stylesheet using postcss AST.
 * - Removes @charset; allows @import only from trusted font providers
 * - Removes @media (prefers-color-scheme: dark) blocks
 * - Removes dangerous CSS (expression(), behavior, -moz-binding, javascript:)
 * - Removes url() with external resources (keeps data: URIs and trusted font URLs)
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

    // Remove url() with external resources, keep data: URIs and trusted font URLs
    if (/url\s*\(/i.test(val) && !/url\s*\(\s*['"]?data:/i.test(val)) {
      // Allow trusted font URLs inside @font-face blocks
      const inFontFace =
        decl.parent &&
        decl.parent.type === "atrule" &&
        decl.parent.name.toLowerCase() === "font-face";
      if (inFontFace && isTrustedFontUrl(val)) {
        // keep it
      } else {
        decl.remove();
      }
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

  // Force links and forms to open in new tab
  if (node.tagName === "A" || node.tagName === "FORM") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

/**
 * Detect whether an email needs padding.
 *
 * Heuristic: if the first significant element(s) in the email set an explicit
 * background color (via style attribute or bgcolor), the email controls its own
 * layout and padding would create an ugly frame.  Otherwise, the email likely
 * assumes a white background and needs padding for readability.
 */
function detectNeedsPadding(html) {
  try {
    const dom = new JSDOM(html);
    const doc = dom.window.document;
    const body = doc.body;
    if (!body) return true;

    // Check the first few root-level elements (skip whitespace text nodes)
    const children = Array.from(body.children);
    // Skip <style> elements — look at actual content elements
    const contentElements = children.filter(
      (el) => el.tagName.toLowerCase() !== "style"
    );
    if (contentElements.length === 0) return true;

    // Check the first content element and its immediate child
    for (const el of contentElements.slice(0, 2)) {
      if (hasExplicitBackground(el)) return false;
      // Also check immediate wrapper children (common pattern: <div><table bgcolor=...>)
      const firstChild = el.children[0];
      if (firstChild && hasExplicitBackground(firstChild)) return false;
    }

    return true;
  } catch (e) {
    return true; // Default to padding on error
  }
}

/**
 * Check if an element has an explicit background color set.
 */
function hasExplicitBackground(el) {
  // Check bgcolor attribute
  if (el.hasAttribute("bgcolor")) return true;

  // Check inline style for background or background-color
  const style = el.getAttribute("style") || "";
  if (/background(-color)?\s*:/i.test(style)) return true;

  return false;
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

    // Detect if the email needs padding by checking whether root-level
    // elements set an explicit background.  Emails with full-width tables
    // and explicit backgrounds (marketing newsletters) look bad with extra
    // padding, while simple HTML emails (GitHub notifications, plain
    // formatted text) need breathing room.
    const needsPadding = detectNeedsPadding(clean);

    process.stdout.write(JSON.stringify({ id, html: clean, error: null, needsPadding }) + "\n");
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
