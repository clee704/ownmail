"""Download controls and schedule persistence for the web interface."""

import os
import stat
import tempfile
import threading
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import abort, current_app, jsonify, request

from ownmail.downloads import DownloadManager
from ownmail.yaml_util import load_yaml

DOWNLOAD_INTERVALS = (
    (0, "Off"),
    (15, "Every 15 minutes"),
    (30, "Every 30 minutes"),
    (60, "Every hour"),
    (360, "Every 6 hours"),
    (1440, "Every day"),
)


def serialize_config_writes(view):
    """Keep each config update and its live state change together."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        with current_app.extensions["config_write_lock"]:
            return view(*args, **kwargs)

    return wrapped


def save_web_config(data, config_path):
    """Replace the config only after the updated YAML has been written."""
    from ownmail.yaml_util import save_yaml

    path = Path(config_path).resolve()
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=".ownmail-config-", dir=path.parent)
    os.close(fd)
    try:
        save_yaml(data, temporary)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _save_interval(config_path, minutes):
    data = load_yaml(config_path)
    data.setdefault("web", {})["download_interval_minutes"] = minutes
    save_web_config(data, config_path)


def register_downloads(app, archive, config_path):
    """Register the download manager and its JSON endpoints."""
    interval = 0
    if config_path:
        try:
            interval = load_yaml(config_path).get("web", {}).get("download_interval_minutes", 0)
        except Exception:
            pass
    if type(interval) is not int or interval not in dict(DOWNLOAD_INTERVALS):
        interval = 0
    manager = DownloadManager(archive.archive_dir, config_path, interval_minutes=interval)
    app.extensions["downloads"] = manager
    app.extensions["config_write_lock"] = threading.RLock()

    def require_json():
        # HTML forms cannot send JSON; validate browser origins as well.
        if not request.is_json:
            abort(415)
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        if origin or referer:
            source = urlsplit(origin if origin else referer)
            target = urlsplit(request.host_url)
            if (source.scheme, source.netloc) != (target.scheme, target.netloc):
                abort(403)

    def status_response(code=200):
        response = jsonify(manager.snapshot())
        response.headers["Cache-Control"] = "no-store"
        return response, code

    @app.get("/downloads")
    def download_status():
        return status_response()

    @app.post("/downloads")
    def start_download():
        require_json()
        if manager.start_download():
            return status_response(202)
        return status_response(409 if manager.snapshot()["running"] else 503)

    @app.post("/downloads/schedule")
    @serialize_config_writes
    def save_download_schedule():
        require_json()
        payload = request.get_json(silent=True)
        minutes = payload.get("interval_minutes") if isinstance(payload, dict) else None
        if type(minutes) is not int or minutes not in dict(DOWNLOAD_INTERVALS):
            return jsonify(error="Choose one of the download intervals."), 400
        if not config_path:
            return jsonify(error="Start the server with a config file to save a schedule."), 503
        try:
            _save_interval(config_path, minutes)
        except Exception:
            return jsonify(error="Could not save the schedule. Check the config file and its permissions."), 500
        manager.set_interval(minutes)
        return status_response()

    return manager
