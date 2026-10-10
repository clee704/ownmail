"""Host header allowlist for the web interface."""

import ipaddress
import re

from flask import Response, request

# Accepted when no allowed hosts are configured. Other names and addresses,
# including the bind address, must be configured explicitly.
LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "[::1]")

HOST_NAME_RE = re.compile(r"[a-z0-9._-]+")
PORT_RE = re.compile(r"[0-9]{1,5}")


def _split_host(value):
    """Split a Host value into a lowercase name and an optional port, or return None."""
    value = value.lower()
    if value.startswith("["):
        address, bracket, rest = value[1:].partition("]")
        if not bracket or (rest and not rest.startswith(":")):
            return None
        try:
            name = f"[{ipaddress.IPv6Address(address).compressed}]"
        except ValueError:
            return None
        port = rest[1:] if rest else None
    else:
        name, colon, port = value.partition(":")
        if not HOST_NAME_RE.fullmatch(name):
            return None
        port = port if colon else None
    if port is None:
        return name, None
    if not PORT_RE.fullmatch(port) or not 0 < int(port) < 65536:
        return None
    return name, int(port)


def _join_host(name, port):
    return name if port is None else f"{name}:{port}"


def normalize_host(value):
    """Return a Host header value as ``name`` or ``name:port`` in canonical form.

    Names are lowercased and IPv6 literals compressed, so equivalent spellings
    compare equal. Returns None for anything that is not a host and optional
    port, such as a URL or an empty value.
    """
    parts = _split_host(value)
    return None if parts is None else _join_host(*parts)


def resolve_allowed_hosts(entries=None, port=None):
    """Return the exact Host values to accept, in configuration order.

    No entries means the loopback names. An entry without a port also accepts
    the serving port; an entry with a port accepts only that port. Raises
    ValueError for an entry that is not a host name or address, or for a
    serving port outside 1-65535.
    """
    if entries is not None and not isinstance(entries, list | tuple):
        raise ValueError("Allowed hosts must be a list of host names or addresses.")
    if port is not None and not 0 < port < 65536:
        raise ValueError(f"Invalid port {port}. Use a port from 1 to 65535.")
    allowed = []
    for entry in entries or LOOPBACK_HOSTS:
        parts = _split_host(entry) if isinstance(entry, str) else None
        if parts is None:
            raise ValueError(
                f"Invalid allowed host {entry!r}. Use a host name or address with an optional port, "
                "such as mail.example, 192.0.2.10:8080, or [::1]."
            )
        name, entry_port = parts
        for value_port in (entry_port,) if entry_port is not None else (None, port):
            value = _join_host(name, value_port)
            if value not in allowed:
                allowed.append(value)
    return tuple(allowed)


def browser_url(bind, port, allowed_hosts):
    """Return an http URL for a browser on this computer, or None if no allowed Host reaches the bind address."""
    if bind in ("0.0.0.0", "::"):
        # Every interface listens, so prefer a loopback name, then any allowed host on the serving port.
        candidates = [*(f"{name}:{port}" for name in LOOPBACK_HOSTS), *allowed_hosts]
    else:
        candidates = [f"[{bind}]:{port}" if ":" in bind else f"{bind}:{port}"]
    for candidate in candidates:
        value = normalize_host(candidate)
        if value in allowed_hosts and value.endswith(f":{port}"):
            return f"http://{value}"
    return None


def register_host_check(app):
    """Answer requests whose Host is not in app.config["allowed_hosts"] with 400.

    Register this before any other request hook. The response is plain text so
    a rejected request never renders application content.
    """

    @app.before_request
    def reject_unknown_host():
        if normalize_host(request.headers.get("Host", "")) not in app.config["allowed_hosts"]:
            return Response("Unrecognized Host header.\n", status=400, mimetype="text/plain")
