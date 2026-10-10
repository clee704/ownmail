"""CSRF tokens and exact-origin checks for state-changing web requests.

Every request other than GET, HEAD and OPTIONS must come from an allowed
origin and carry a token, so no view may change state on those three methods.
The token is an HMAC of a random value kept in a host-only, HttpOnly,
SameSite=Strict cookie, signed with a key made at process start. Only a page
this server rendered for the same browser can supply it, and a restart
replaces the key, which expires every earlier token.
"""

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

from flask import Response, g, jsonify, request

from ownmail.web_hosts import normalize_host

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
COOKIE_NAME = "ownmail_csrf"
HEADER_NAME = "X-CSRF-Token"
FIELD_NAME = "csrf_token"
# "token" tells trusted scripts that a fresh token may succeed; "origin" never will.
REJECTED_HEADER = "X-CSRF-Rejected"
DEFAULT_PORTS = {"http": 80, "https": 443}
NONCE_RE = re.compile(r"[A-Za-z0-9_-]{43}")

ORIGIN_MESSAGE = "Request rejected: it did not come from an allowed origin."
EXPIRED_MESSAGE = "This page expired, for example because the server restarted. Reload the page and try again."


def _canonical_origin(value):
    """Return ``scheme://host[:port]`` as browsers serialize it, or None."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if (
        scheme not in DEFAULT_PORTS
        or "@" in parts.netloc
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        return None
    host = normalize_host(parts.netloc)
    if host is None:
        return None
    return f"{scheme}://{host.removesuffix(f':{DEFAULT_PORTS[scheme]}')}"


def resolve_allowed_origins(entries=None):
    """Return configured browser origins in canonical form, or () when none are set.

    Raises ValueError for an entry that is not a scheme, host and optional port.
    """
    if entries is not None and not isinstance(entries, list | tuple):
        raise ValueError("Allowed origins must be a list of origins.")
    origins = []
    for entry in entries or ():
        origin = _canonical_origin(entry) if isinstance(entry, str) else None
        if origin is None:
            raise ValueError(
                f"Invalid allowed origin {entry!r}. Use http:// or https:// with a host name or address "
                "and an optional port, such as https://mail.example."
            )
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)


def sign(key, nonce):
    """Return the token for a cookie value under one process key."""
    digest = hmac.new(key, nonce.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def register_csrf_protection(app):
    """Check the origin and token of every state-changing request before any handler runs.

    Register this right after the Host check. Accepted origins are the
    request's own origin, from its scheme and the Host the check accepted, and
    app.config["allowed_origins"]. Templates get csrf_token(), and GET
    /csrf-token returns a fresh token for pages rendered under an earlier key.
    """
    key = secrets.token_bytes(32)

    def nonce():
        if "csrf_nonce" not in g:
            value = request.cookies.get(COOKIE_NAME, "")
            g.csrf_new_nonce = not NONCE_RE.fullmatch(value)
            g.csrf_nonce = secrets.token_urlsafe(32) if g.csrf_new_nonce else value
        return g.csrf_nonce

    def csrf_token():
        g.csrf_token_sent = True
        return sign(key, nonce())

    def own_origin(scheme):
        return _canonical_origin(f"{scheme}://{request.host}")

    def origin_allowed():
        # Exact origins only: browsers send the cookie to every port on a host,
        # so a page on another port or under another allowed name must not pass.
        allowed = {own_origin(request.scheme), *app.config["allowed_origins"]}
        origin = request.headers.get("Origin")
        if origin is not None:
            return origin in allowed
        try:
            referer = urlsplit(request.headers.get("Referer", ""))
        except ValueError:
            return False
        return f"{referer.scheme}://{referer.netloc}" in allowed

    def token_valid():
        supplied = request.headers.get(HEADER_NAME)
        if supplied is None:
            supplied = request.form.get(FIELD_NAME, "")
        value = request.cookies.get(COOKIE_NAME, "")
        return bool(NONCE_RE.fullmatch(value)) and hmac.compare_digest(supplied.encode(), sign(key, value).encode())

    def reject(reason, message):
        # Scripts send the token header; a plain form post gets readable text.
        if HEADER_NAME in request.headers:
            response = jsonify(error=message)
        else:
            response = Response(message + "\n", mimetype="text/plain")
        response.status_code = 403
        response.headers[REJECTED_HEADER] = reason
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def check_state_changing_request():
        if request.method in SAFE_METHODS:
            return None
        if not origin_allowed():
            return reject("origin", ORIGIN_MESSAGE)
        if not token_valid():
            return reject("token", EXPIRED_MESSAGE)
        return None

    def cookie_secure():
        # Behind a TLS-terminating proxy the request is plain HTTP, but its Host
        # names a configured https origin. X-Forwarded-* headers are not read.
        return request.is_secure or own_origin("https") in app.config["allowed_origins"]

    @app.after_request
    def protect_token_response(response):
        if g.get("csrf_new_nonce"):
            response.set_cookie(COOKIE_NAME, g.csrf_nonce, secure=cookie_secure(), httponly=True, samesite="Strict")
        if g.get("csrf_token_sent"):
            # No cache may keep a page or response that carries a token.
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/csrf-token")
    def fresh_csrf_token():
        response = jsonify(token=csrf_token())
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # A context processor, unlike a Jinja global, leaves the template environment
    # uncreated, so run_server can still enable template reloading.
    @app.context_processor
    def provide_csrf_token():
        return {"csrf_token": csrf_token}
