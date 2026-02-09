"""Web interface for browsing and searching the email archive."""

import email

from flask import Flask, abort, render_template_string, request, send_file

from ownmail.archive import EmailArchive


def create_app(archive: EmailArchive) -> Flask:
    """Create the Flask application.

    Args:
        archive: EmailArchive instance

    Returns:
        Flask application
    """
    app = Flask(__name__)
    app.config["archive"] = archive

    # HTML Templates
    BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}ownmail{% endblock %}</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }
        header h1 { margin: 0; font-size: 1.5em; }
        header h1 a { color: inherit; text-decoration: none; }
        .stats { color: #666; font-size: 0.9em; }
        .search-form {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .search-form input[type="text"] {
            flex: 1;
            padding: 10px 15px;
            font-size: 16px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .search-form button {
            padding: 10px 20px;
            font-size: 16px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        .search-form button:hover { background: #0052a3; }
        .email-list { list-style: none; padding: 0; }
        .email-item {
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        .email-item:hover { border-color: #0066cc; }
        .email-item a { text-decoration: none; color: inherit; display: block; }
        .email-subject { font-weight: 600; margin-bottom: 5px; color: #0066cc; }
        .email-meta { font-size: 0.9em; color: #666; }
        .email-snippet { font-size: 0.9em; color: #888; margin-top: 5px; }
        .email-detail {
            background: white;
            padding: 20px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        .email-header { margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
        .email-header h2 { margin: 0 0 10px 0; }
        .email-header-row { margin: 5px 0; }
        .email-header-label { font-weight: 600; display: inline-block; width: 80px; }
        .email-body {
            white-space: pre-wrap;
            font-family: inherit;
            line-height: 1.6;
        }
        .email-body-html { line-height: 1.6; }
        .back-link { margin-bottom: 15px; }
        .back-link a { color: #0066cc; }
        .no-results { color: #666; text-align: center; padding: 40px; }
        .attachments { margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }
        .attachments h4 { margin: 0 0 10px 0; }
        .attachment-list { list-style: none; padding: 0; }
        .attachment-item { padding: 5px 0; }
        .attachment-item a { color: #0066cc; }
        .labels { margin-top: 10px; }
        .label {
            display: inline-block;
            background: #e0e0e0;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            margin-right: 5px;
        }
        .help { font-size: 0.85em; color: #666; margin-top: 10px; }
    </style>
</head>
<body>
    <header>
        <h1><a href="/">📧 ownmail</a></h1>
        <div class="stats">{{ stats.total_emails | default(0) }} emails archived</div>
    </header>
    {% block content %}{% endblock %}
</body>
</html>
"""

    SEARCH_TEMPLATE = BASE_TEMPLATE.replace(
        "{% block title %}ownmail{% endblock %}",
        "{% block title %}Search - ownmail{% endblock %}"
    ).replace(
        "{% block content %}{% endblock %}",
        """{% block content %}
    <form class="search-form" action="/search" method="get">
        <input type="text" name="q" value="{{ query | default('') }}" placeholder="Search emails..." autofocus>
        <button type="submit">Search</button>
    </form>
    <div class="help">
        Search tips: <code>from:sender</code>, <code>subject:topic</code>, <code>attachment:filename</code>
    </div>

    {% if query %}
        {% if results %}
            <p>Found {{ results | length }} result(s) for "{{ query }}"</p>
            <ul class="email-list">
            {% for result in results %}
                <li class="email-item">
                    <a href="/email/{{ result.message_id }}">
                        <div class="email-subject">{{ result.subject or '(No subject)' }}</div>
                        <div class="email-meta">
                            From: {{ result.sender }} &bull; {{ result.date_str }}
                        </div>
                        <div class="email-snippet">{{ result.snippet }}</div>
                    </a>
                </li>
            {% endfor %}
            </ul>
        {% else %}
            <div class="no-results">No results found for "{{ query }}"</div>
        {% endif %}
    {% else %}
        <div class="no-results">Enter a search query to find emails</div>
    {% endif %}
{% endblock %}"""
    )

    EMAIL_TEMPLATE = BASE_TEMPLATE.replace(
        "{% block title %}ownmail{% endblock %}",
        "{% block title %}{{ subject }} - ownmail{% endblock %}"
    ).replace(
        "{% block content %}{% endblock %}",
        """{% block content %}
    <div class="back-link"><a href="javascript:history.back()">&larr; Back to search</a></div>
    <div class="email-detail">
        <div class="email-header">
            <h2>{{ subject or '(No subject)' }}</h2>
            <div class="email-header-row">
                <span class="email-header-label">From:</span> {{ sender }}
            </div>
            <div class="email-header-row">
                <span class="email-header-label">To:</span> {{ recipients }}
            </div>
            <div class="email-header-row">
                <span class="email-header-label">Date:</span> {{ date }}
            </div>
            {% if labels %}
            <div class="labels">
                {% for label in labels %}
                <span class="label">{{ label }}</span>
                {% endfor %}
            </div>
            {% endif %}
        </div>

        {% if body_html %}
            <div class="email-body-html">{{ body_html | safe }}</div>
        {% else %}
            <pre class="email-body">{{ body }}</pre>
        {% endif %}

        {% if attachments %}
        <div class="attachments">
            <h4>Attachments</h4>
            <ul class="attachment-list">
            {% for att in attachments %}
                <li class="attachment-item">
                    <a href="/attachment/{{ message_id }}/{{ loop.index0 }}">📎 {{ att.filename }}</a>
                    ({{ att.size }})
                </li>
            {% endfor %}
            </ul>
        </div>
        {% endif %}
    </div>
{% endblock %}"""
    )

    @app.route("/")
    def index():
        stats = archive.db.get_stats()
        return render_template_string(SEARCH_TEMPLATE, stats=stats, query="", results=None)

    @app.route("/search")
    def search():
        query = request.args.get("q", "").strip()
        stats = archive.db.get_stats()

        if not query:
            return render_template_string(SEARCH_TEMPLATE, stats=stats, query="", results=None)

        # Search
        raw_results = archive.search(query, limit=100)

        # Format results
        results = []
        for msg_id, filename, subject, sender, date_str, snippet in raw_results:
            results.append({
                "message_id": msg_id,
                "filename": filename,
                "subject": subject,
                "sender": sender,
                "date_str": date_str,
                "snippet": snippet,
            })

        return render_template_string(SEARCH_TEMPLATE, stats=stats, query=query, results=results)

    @app.route("/email/<message_id>")
    def view_email(message_id: str):
        stats = archive.db.get_stats()

        # Get email file path from database
        email_info = archive.db.get_email_by_id(message_id)
        if not email_info:
            abort(404)

        filename = email_info[1]  # filename is second column
        filepath = archive.archive_dir / filename

        if not filepath.exists():
            abort(404)

        # Parse email
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f)

        subject = msg.get("Subject", "(No subject)")
        sender = msg.get("From", "")
        recipients = msg.get("To", "")
        date = msg.get("Date", "")

        # Get labels from X-Gmail-Labels header
        labels = []
        gmail_labels = msg.get("X-Gmail-Labels", "")
        if gmail_labels:
            labels = [lbl.strip() for lbl in gmail_labels.split(",")]

        # Extract body
        body = ""
        body_html = None
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    # Attachment
                    filename = part.get_filename() or "attachment"
                    size = len(part.get_payload(decode=True) or b"")
                    attachments.append({
                        "filename": filename,
                        "size": _format_size(size),
                    })
                elif content_type == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body = payload.decode(charset, errors="replace")
                        except Exception:
                            body = payload.decode("utf-8", errors="replace")
                elif content_type == "text/html" and not body_html:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_html = payload.decode(charset, errors="replace")
                        except Exception:
                            body_html = payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    body = payload.decode(charset, errors="replace")
                except Exception:
                    body = payload.decode("utf-8", errors="replace")

        # Prefer plain text over HTML for security
        if body:
            body_html = None

        return render_template_string(
            EMAIL_TEMPLATE,
            stats=stats,
            message_id=message_id,
            subject=subject,
            sender=sender,
            recipients=recipients,
            date=date,
            labels=labels,
            body=body,
            body_html=body_html,
            attachments=attachments,
        )

    @app.route("/attachment/<message_id>/<int:index>")
    def download_attachment(message_id: str, index: int):
        # Get email file path
        email_info = archive.db.get_email_by_id(message_id)
        if not email_info:
            abort(404)

        filename = email_info[1]
        filepath = archive.archive_dir / filename

        if not filepath.exists():
            abort(404)

        # Parse email and find attachment
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f)

        attachment_idx = 0
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                if attachment_idx == index:
                    # Found the attachment
                    att_filename = part.get_filename() or "attachment"
                    att_data = part.get_payload(decode=True)
                    content_type = part.get_content_type()

                    # Create temp file and send
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp.write(att_data)
                        tmp_path = tmp.name

                    return send_file(
                        tmp_path,
                        mimetype=content_type,
                        as_attachment=True,
                        download_name=att_filename,
                    )
                attachment_idx += 1

        abort(404)

    return app


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def run_server(
    archive: EmailArchive,
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
) -> None:
    """Run the web server.

    Args:
        archive: EmailArchive instance
        host: Host to bind to
        port: Port to listen on
        debug: Enable debug mode
    """
    app = create_app(archive)

    print("\n🌐 ownmail web interface")
    print(f"   Running at: http://{host}:{port}")
    print("   Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=debug)
