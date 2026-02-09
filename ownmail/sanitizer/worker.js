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

  // Keep the full document structure (html/head/body) if present
  WHOLE_DOCUMENT: true,
  // Return string, not DOM node
  RETURN_DOM: false,
  RETURN_DOM_FRAGMENT: false,
};

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

// Hook into DOMPurify to sanitize CSS
purify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName === "style" && node.textContent) {
    node.textContent = sanitizeCSS(node.textContent);
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
