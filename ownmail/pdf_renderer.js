"use strict";

// Optional renderer: no installer, application server or persistent browser profile.
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const requireSanitizer = createRequire(path.join(__dirname, "sanitizer", "package.json"));
const DOCUMENT_URL = "https://ownmail-pdf.invalid/message";
const CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; sandbox";
// Export prints on A4. Wide messages are fitted to the width between
// pdf.html's 14mm page margins, so they are measured at that width.
const CONTENT_VIEWPORT = {width: Math.round((210 - 2 * 14) * 96 / 25.4), height: 1123};

async function deadline(promise, milliseconds) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("PDF rendering timed out")), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

// Closing only releases resources once the PDF is written, so a slow close must
// not fail the export. Exiting at the end lets Playwright kill a browser still
// closing; render failures already propagate from the try block.
async function closeWithin(promise, milliseconds) {
  await deadline(promise, milliseconds).catch(() => {});
}

async function main() {
  const { chromium } = requireSanitizer("playwright");
  const executablePath = process.env.OWNMAIL_BROWSER_EXECUTABLE || chromium.executablePath();
  fs.accessSync(executablePath, fs.constants.X_OK);
  if (process.argv[2] === "--check") return;
  const directory = process.argv[2];
  const count = Number(process.argv[3]);
  if (!directory || !Number.isSafeInteger(count) || count < 1) throw new Error("Invalid PDF render request");
  const browser = await chromium.launch({headless: true, chromiumSandbox: true, executablePath, timeout: 30000});
  try {
    for (let index = 1; index <= count; index++) {
      const name = String(index).padStart(6, "0");
      const html = fs.readFileSync(path.join(directory, name + ".html"), "utf8");
      const context = await browser.newContext({
        javaScriptEnabled: false, serviceWorkers: "block", acceptDownloads: false,
        offline: true, colorScheme: "light", viewport: CONTENT_VIEWPORT,
      });
      try {
        const page = await context.newPage();
        let supplied = false;
        await context.route("**/*", async route => {
          const request = route.request();
          if (!supplied && request.url() === DOCUMENT_URL && request.isNavigationRequest() && request.frame() === page.mainFrame()) {
            supplied = true;
            await route.fulfill({status: 200, contentType: "text/html; charset=utf-8", headers: {"Content-Security-Policy": CSP}, body: html});
          } else {
            await route.abort();
          }
        });
        await deadline((async () => {
          await page.emulateMedia({media: "print"});
          await page.goto(DOCUMENT_URL, {waitUntil: "load", timeout: 15000});
          // Trusted layout measurement remains available with page scripts disabled.
          await page.evaluate(() => {
            const body = document.getElementById("ownmail-email-content");
            const frame = document.getElementById("ownmail-pdf-body");
            if (body && frame && body.scrollWidth > frame.clientWidth) {
              body.style.zoom = String(frame.clientWidth / body.scrollWidth);
            }
          });
          await page.pdf({path: path.join(directory, name + ".pdf"), format: "A4", printBackground: true, preferCSSPageSize: true});
        })(), 45000);
      } finally {
        await closeWithin(context.close(), 5000);
      }
    }
  } finally {
    await closeWithin(browser.close(), 5000);
  }
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(() => process.exit());
