---
id: TASK-31
title: Attachment preview — view in browser instead of always downloading
status: Done
assignee: []
created_date: '2026-07-31 19:13'
updated_date: '2026-07-31 19:33'
labels:
  - enhancement
dependencies: []
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Clicking an attachment always downloads it: the route passes as_attachment=True unconditionally. PDFs and images should open in the browser, with download still available explicitly.

UI (chosen with the maintainer): the filename stays the link and now opens an inline preview in a new tab; a download icon sits at the right of each row. Types the browser cannot safely render fall back to downloading from the name, so every row keeps the same shape.

Security: the route currently echoes the part's Content-Type straight from the email, which is attacker-controlled, and the app sets no CSP or nosniff headers anywhere. Serving inline naively would let anyone who can email the user execute script on the archive's own origin and read mail via /email/<id>. Inline is therefore restricted to a safelist the browser renders without scripting (PDF, raster images, plain text, audio, video), SVG explicitly excluded, with the response Content-Type sent from the safelist rather than from the email, plus X-Content-Type-Options: nosniff and Content-Security-Policy: default-src 'none'; sandbox.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Safelisted types render inline; everything else still downloads
- [x] #2 Download remains available for every attachment regardless of type
- [x] #3 Inline responses send a safelisted Content-Type, nosniff, and a sandboxing CSP
- [x] #4 SVG and HTML attachments are never served inline
- [x] #5 Tests cover inline vs download disposition and the security headers
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Route takes `?download` as the explicit save action; without it a part whose type is in INLINE_SAFE_TYPES is sent with Content-Disposition: inline.

Security shape:
- The response Content-Type is the safelisted string, never the one the message declared, so a mislabelled part cannot talk the browser into rendering something else.
- Downloads go out as application/octet-stream for the same reason; the filename still carries the extension.
- Every response carries X-Content-Type-Options: nosniff. Inline ones also carry Content-Security-Policy: default-src 'none'; sandbox, which drops them into an opaque origin so they cannot reach the archive around them.
- image/svg+xml is excluded from the safelist deliberately — SVG can carry <script>. text/html likewise never renders inline.
- For text/plain the declared charset is kept so CJK text reads correctly, but only after it matches a charset-shaped pattern and codecs recognizes it. The declared spelling ships rather than codecs' canonical name, which uses underscores (euc_kr) that no browser knows. Werkzeug appends its own charset to any text/* mimetype, so the header is set explicitly to avoid emitting two.

UI: filename stays the link and opens the preview in a new tab; a download icon sits at the right of every row; a type glyph and 'KIND · size' line replace the bare size. Both places the template's attachment dicts were built now go through one _attachment_entry helper.

Checked in a real browser against a scratch archive holding a PDF, PNG, SVG, ZIP and an EUC-KR text file. The PNG renders inline, the EUC-KR text renders as Hangul rather than mojibake, SVG and ZIP download, and ?download turns the PDF into a save.

On PDFs specifically: the browser used for the check has its PDF viewer switched off, so PDFs download rather than render. Serving the same PDF with the CSP and with no CSP at all behaved identically — Chrome's placeholder with an Open button in both — so the sandbox header is not what stops it. Anyone whose browser is set to open PDFs will get the preview; it is a browser preference, not something the response controls.
<!-- SECTION:NOTES:END -->
