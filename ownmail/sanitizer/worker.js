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

// Trusted font provider domains (for @import and @font-face url())
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
  // Split on commas, trim, and check the last entry
  const parts = value.split(",").map((s) => s.trim().replace(/['"]*/g, "").toLowerCase());
  const last = parts[parts.length - 1];
  if (last && GENERIC_FONT_FAMILIES.has(last)) {
    return value;
  }
  return value + ", sans-serif";
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
 * Scope and sanitize a CSS stylesheet using postcss AST.
 * - Removes @charset; allows @import only from trusted font providers
 * - Removes dangerous CSS (expression(), behavior, -moz-binding, javascript:)
 * - Removes url() with external resources (keeps data: URIs and trusted font URLs)
 * - Scopes all selectors under #ownmail-email-content
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

    // Allow external url() — image blocking is handled server-side in Python.
    // Only strip url() with javascript: scheme (security risk).
    if (/url\s*\(\s*['"]?javascript:/i.test(val)) {
      decl.remove();
      return;
    }

    // Ensure font-family declarations end with a generic fallback
    if (prop === "font-family" || prop === "font") {
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
  // Remove javascript: URLs (security risk) but allow external image URLs
  // (image blocking is handled server-side in Python)
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

// Hook into DOMPurify to sanitize and scope CSS, and filter <link> tags
purify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName === "style" && node.textContent) {
    node.textContent = scopeAndSanitizeCSS(node.textContent);
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

  // Force links and forms to open in new tab
  if (node.tagName === "A" || node.tagName === "FORM") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

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
      if (/prefers-color-scheme\s*:\s*dark/i.test(style.textContent)) {
        return true;
      }
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
