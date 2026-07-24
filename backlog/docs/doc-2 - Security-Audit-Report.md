---
id: doc-2
title: Security Audit Report
type: other
created_date: '2026-02-09 00:00'
---

**Scope:** Full codebase review (source, dependencies, git history)
**Overall Rating:** **A (Very Good)** ✅

No critical or high-severity issues found. The codebase demonstrates strong security awareness.

---

## ✅ What's Done Well

| Area | Assessment |
|------|-----------|
| **Credential storage** | Uses OS keychain via `keyring` — no plaintext secrets anywhere |
| **No hardcoded secrets** | Scanned code + full git history — clean |
| **SQL injection** | All queries use parameterized `?` placeholders — safe |
| **XSS protection** | DOMPurify (industry standard) sanitizes HTML emails; Jinja2 auto-escaping on |
| **CSRF protection** | Origin/Referer validation on all POST endpoints |
| **Path traversal** | `.resolve()` + `is_relative_to()` checks on all file-serving routes |
| **Open redirects** | Redirect targets validated to start with `/` |
| **Email HTML sandboxing** | CSS scoped, dangerous tags stripped, external images blocked by default |
| **Password input** | Uses `getpass.getpass()` — hidden in terminal |
| **File writes** | Atomic via `mkstemp()` + rename |
| **Binds to localhost** | Default `127.0.0.1:8080` — not exposed to network |
| **Debug mode** | Not hardcoded; passed as parameter |
| **Dependencies** | All up-to-date, no known CVEs in project dependencies |

---

## ⚠️ Low/Medium Findings

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | **Medium** | Generic `except Exception` may leak sensitive info via `str(e)` (e.g., server hostnames, API errors) | `providers/gmail.py:79-81`, `providers/imap.py:100-107` |
| 2 | **Low** | No HTTP security headers (CSP, X-Content-Type-Options, X-Frame-Options) | `web.py` — acceptable for local-only app |
| 3 | **Low** | No query length limit — extremely long search strings could cause slowness | `query.py` |
| 4 | **Low** | Debug `print()` statements in search path could log email metadata to stdout | `database.py` |

---

## 💡 Recommendations (Optional Hardening)

### 1. Catch specific exceptions in providers

Avoid leaking server details in error messages. Use specific exception types
(`HttpError`, `RefreshError`, `IMAP4.error`) instead of bare `Exception`.

### 2. Add security headers (if exposing web UI beyond localhost)

```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response
```

### 3. Add a search query length limit

Cap search queries (e.g., 1000 characters) in `query.py` to prevent potential
DoS via extremely long inputs.

### 4. Pin upper bounds on dependencies

Consider pinning upper bounds in `pyproject.toml` to avoid surprise breaking
changes (e.g., `flask>=2.0.0,<4`).

---

## Detailed Analysis

### Credential Handling (`keychain.py`, `config.py`, `providers/`)

- All credentials (OAuth tokens, IMAP passwords, client secrets) stored in OS
  keychain via the `keyring` library — never written to disk.
- Config file uses `secret_ref: keychain:...` references instead of inline
  credentials.
- `getpass.getpass()` used for password input (hidden in terminal).
- No credentials logged or printed to stdout.

### Web Security (`web.py`, `sanitizer/`, `templates/`)

- **XSS:** HTML emails sanitized by DOMPurify running in a Node.js sidecar.
  Dangerous tags (`<script>`, `<iframe>`, `<object>`, etc.) stripped. CSS
  scoped under `#ownmail-email-content` to prevent style leakage. Falls back
  to HTML escaping if Node.js is unavailable.
- **CSRF:** All POST endpoints (`/trust-sender`, `/untrust-sender`,
  `/settings`) validate `Origin`/`Referer` headers. Requests without a valid
  origin are rejected with 403.
- **Path traversal:** File-serving routes use `Path.resolve()` +
  `is_relative_to()` to ensure files are within the archive directory.
- **Open redirects:** Redirect targets validated to be relative paths
  (starting with `/`).
- **Image blocking:** External images blocked by default for privacy. Users
  can whitelist trusted senders.

### Database & Query (`database.py`, `query.py`)

- All SQL uses parameterized queries with `?` placeholders — no string
  concatenation.
- FTS5 search queries properly escaped via `_escape_fts5_value()`.
- User input tokenized and validated before translation to SQL.
- No `eval()`, `exec()`, or dynamic code execution.

### Email Parsing (`parser.py`)

- Header injection prevented: `_sanitize_header()` strips CR/LF characters.
- Robust charset handling with fallback chains.
- No unsafe deserialization — uses standard library `email.message_from_bytes()`.

### File Operations (`archive.py`)

- Atomic writes via `mkstemp()` + `os.rename()`.
- No shell commands or subprocess calls.
- File paths constructed with `pathlib.Path` (safe).

### Git History

- No secrets, credentials, or private keys found in any commit.

### Dependencies (as of 2026-02-09)

| Package | Version | Status |
|---------|---------|--------|
| Flask | 3.1.2 | ✅ No known CVEs |
| Jinja2 | 3.1.6 | ✅ No known CVEs |
| Werkzeug | 3.1.3 | ✅ No known CVEs |
| lxml | 6.0.2 | ✅ No known CVEs |
| google-auth | 2.48.0 | ✅ No known CVEs |
| google-auth-oauthlib | 1.2.4 | ✅ No known CVEs |
| google-api-python-client | 2.189.0 | ✅ No known CVEs |
| keyring | 25.7.0 | ✅ No known CVEs |
| ruamel.yaml | 0.19.1 | ✅ No known CVEs |
| MarkupSafe | 3.0.3 | ✅ No known CVEs |
