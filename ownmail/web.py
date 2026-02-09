"""Web interface for browsing and searching the email archive."""

import email
import email.header
import re
import time

from flask import Flask, abort, g, render_template_string, request, send_file

from ownmail.archive import EmailArchive

# Regex to find external images in HTML
EXTERNAL_IMAGE_RE = re.compile(
    r'<img\s+([^>]*\s)?src\s*=\s*["\']?(https?://[^"\'>\s]+)["\']?',
    re.IGNORECASE,
)


def decode_header(value: str) -> str:
    """Decode MIME encoded header (RFC 2047)."""
    if not value:
        return ""
    try:
        decoded_parts = email.header.decode_header(value)
        result = []
        for data, charset in decoded_parts:
            if isinstance(data, bytes):
                result.append(data.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(data)
        return "".join(result)
    except Exception:
        return value


def _extract_snippet(msg: email.message.Message, max_len: int = 150) -> str:
    """Extract a text snippet from email body for preview."""
    try:
        # Try to get plain text part first
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        # Clean up whitespace
                        text = " ".join(text.split())
                        return text[:max_len] + "..." if len(text) > max_len else text
        else:
            if msg.get_content_type() == "text/plain":
                payload = msg.get_payload(decode=True)
                if payload:
                    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                    text = " ".join(text.split())
                    return text[:max_len] + "..." if len(text) > max_len else text
    except Exception:
        pass
    return ""


def block_external_images(html: str) -> tuple[str, bool]:
    """Block external images in HTML by replacing src with data-src.

    Args:
        html: HTML content

    Returns:
        Tuple of (modified HTML, whether external images were found)
    """
    has_external = bool(EXTERNAL_IMAGE_RE.search(html))
    if not has_external:
        return html, False

    def replace_src(match):
        prefix = match.group(1) or ""
        url = match.group(2)
        return f'<img {prefix}data-src="{url}" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"'

    blocked_html = EXTERNAL_IMAGE_RE.sub(replace_src, html)
    return blocked_html, True


def parse_email_address(addr: str) -> tuple:
    """Parse email address into (name, email) tuple.

    Args:
        addr: Email address string like "John Doe <john@example.com>" or "john@example.com"

    Returns:
        Tuple of (name, email) where name may be empty
    """
    if not addr:
        return ("", "")

    # Try to match "Name <email>" format
    match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>$', addr.strip())
    if match:
        name = match.group(1).strip()
        email_addr = match.group(2).strip()
        return (name, email_addr)

    # Try to match just email
    match = re.match(r'^<?([^@\s]+@[^>\s]+)>?$', addr.strip())
    if match:
        return ("", match.group(1))

    return ("", "")


def parse_recipients(recipients_str: str) -> list:
    """Parse recipients string into list of parsed addresses.

    Args:
        recipients_str: Comma-separated recipients

    Returns:
        List of dicts with 'name', 'email', 'raw' keys
    """
    if not recipients_str:
        return []

    result = []
    # Split on comma but be careful of commas inside quotes
    parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', recipients_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        name, email_addr = parse_email_address(part)
        result.append({
            "name": name,
            "email": email_addr,
            "raw": part,
        })
    return result


class LRUCache:
    """Simple LRU cache with TTL."""

    def __init__(self, maxsize: int = 100, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl  # seconds
        self.cache = {}  # key -> (value, timestamp)
        self.order = []  # keys in access order

    def get(self, key):
        """Get value from cache, or None if not found/expired."""
        if key not in self.cache:
            return None
        value, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl:
            # Expired
            del self.cache[key]
            if key in self.order:
                self.order.remove(key)
            return None
        # Move to end (most recently used)
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)
        return value

    def set(self, key, value):
        """Set value in cache."""
        # Remove oldest if at capacity
        while len(self.cache) >= self.maxsize and self.order:
            oldest = self.order.pop(0)
            if oldest in self.cache:
                del self.cache[oldest]
        self.cache[key] = (value, time.time())
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)


def create_app(archive: EmailArchive, verbose: bool = False, block_images: bool = False, page_size: int = 20) -> Flask:
    """Create the Flask application.

    Args:
        archive: EmailArchive instance
        verbose: Enable request timing logs
        block_images: Block external images by default
        page_size: Number of results per page

    Returns:
        Flask application
    """
    app = Flask(__name__)
    app.config["archive"] = archive
    app.config["verbose"] = verbose
    app.config["block_images"] = block_images
    app.config["page_size"] = page_size

    # Cache for stats (refreshed every 60 seconds)
    stats_cache = {"value": None, "time": 0}

    # Cache for search results (100 queries, 5 min TTL)
    search_cache = LRUCache(maxsize=100, ttl=300)

    # Cache for parsed emails (50 emails, 10 min TTL)
    email_cache = LRUCache(maxsize=50, ttl=600)

    def get_cached_stats():
        """Get stats with caching to avoid slow DB queries on every request."""
        now = time.time()
        if stats_cache["value"] is None or now - stats_cache["time"] > 60:
            if verbose:
                print("[verbose] Refreshing stats cache...", flush=True)
            start = time.time()
            # Use fast email count instead of slow get_stats
            total = archive.db.get_email_count()
            stats_cache["value"] = {"total_emails": total}
            stats_cache["time"] = now
            if verbose:
                print(f"[verbose] Stats query took {time.time()-start:.2f}s", flush=True)
        return stats_cache["value"]

    if verbose:
        @app.before_request
        def before_request():
            g.start_time = time.time()

        @app.after_request
        def after_request(response):
            if hasattr(g, "start_time"):
                elapsed = time.time() - g.start_time
                print(f"[{request.method}] {request.path} - {elapsed:.2f}s", flush=True)
            return response

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
        .sort-select {
            padding: 10px 15px;
            font-size: 16px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background: white;
            cursor: pointer;
        }
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
        .email-body-html {
            width: 100%;
            min-height: 300px;
            border: none;
            background: white;
        }
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
        .clickable-label {
            text-decoration: none;
            color: inherit;
            cursor: pointer;
        }
        .clickable-label:hover {
            background: #c0c0c0;
        }
        .clickable-header {
            color: #0066cc;
            text-decoration: none;
        }
        .clickable-header:hover {
            text-decoration: underline;
        }
        .help { font-size: 0.85em; color: #666; margin-top: 10px; }
        .help a { color: #0066cc; }
        .help-page { max-width: 700px; margin: 0 auto; }
        .help-page h2 { margin-bottom: 20px; }
        .help-page h3 { margin-top: 25px; margin-bottom: 10px; color: #333; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .help-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
        .help-table td { padding: 8px; border-bottom: 1px solid #eee; }
        .help-table td:first-child { width: 45%; font-family: monospace; background: #f8f8f8; }
        .help-table code { background: transparent; }
        .pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin: 20px 0;
        }
        .pagination a, .pagination span {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            text-decoration: none;
            color: #0066cc;
        }
        .pagination a:hover { background: #e8f0fe; }
        .pagination .current {
            background: #0066cc;
            color: white;
            border-color: #0066cc;
        }
        .pagination .disabled {
            color: #999;
            cursor: default;
        }
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding: 10px 0;
            border-bottom: 1px solid #ddd;
        }
        .results-header p { margin: 0; color: #666; }
        .results-header .pagination { margin: 0; }
        .image-banner {
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 10px 15px;
            border-radius: 5px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .image-banner button {
            background: #0066cc;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 3px;
            cursor: pointer;
        }
        .image-banner button:hover { background: #0052a3; }
        /* Loading overlay */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        .loading-overlay.show { display: flex; }
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #ddd;
            border-top-color: #0066cc;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .loading-text {
            margin-top: 15px;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="loading-overlay" id="loading">
        <div class="spinner"></div>
        <div class="loading-text" id="loading-text">Loading...</div>
    </div>
    <header>
        <h1><a href="/">📧 ownmail</a></h1>
        <div class="stats">{{ stats.total_emails | default(0) }} emails archived</div>
    </header>
    {% block content %}{% endblock %}
    <script>
    function showLoading(text) {
        document.getElementById('loading-text').textContent = text || 'Loading...';
        document.getElementById('loading').classList.add('show');
    }
    function hideLoading() {
        document.getElementById('loading').classList.remove('show');
    }
    // Hide loading on pageshow (handles back button with bfcache)
    window.addEventListener('pageshow', function(event) {
        hideLoading();
    });
    // Show loading on search form submit
    document.addEventListener('DOMContentLoaded', function() {
        var form = document.querySelector('.search-form');
        if (form) {
            form.addEventListener('submit', function() {
                showLoading('Searching...');
            });
        }
        // Show loading on email link clicks
        document.querySelectorAll('.email-item a').forEach(function(link) {
            link.addEventListener('click', function() {
                showLoading('Loading email...');
            });
        });
        // Show loading on pagination clicks
        document.querySelectorAll('.pagination a').forEach(function(link) {
            link.addEventListener('click', function() {
                showLoading('Loading...');
            });
        });
    });
    </script>
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
        <select name="sort" class="sort-select">
            <option value="relevance" {{ 'selected' if sort == 'relevance' else '' }}>Relevance</option>
            <option value="date_desc" {{ 'selected' if sort == 'date_desc' else '' }}>Newest first</option>
            <option value="date_asc" {{ 'selected' if sort == 'date_asc' else '' }}>Oldest first</option>
        </select>
        <button type="submit">Search</button>
    </form>
    <div class="help">
        Search: <code>from:</code> <code>subject:</code> <code>attachment:</code> <code>before:2024-01-01</code> <code>after:2023-06-15</code> <code>label:INBOX</code>
        &bull; <a href="/help">Syntax help</a>
    </div>

    {% if query %}
        {% if results %}
            <div class="results-header">
                <p>Showing {{ start_idx + 1 }}&ndash;{{ start_idx + results|length }}{% if has_more %}+{% endif %}</p>
                {% if has_prev or has_more %}
                <div class="pagination">
                    {% if has_prev %}
                        <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page - 1 }}">&laquo; Previous</a>
                    {% endif %}
                    <span class="current">Page {{ page }}</span>
                    {% if has_more %}
                        <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page + 1 }}">Next &raquo;</a>
                    {% endif %}
                </div>
                {% endif %}
            </div>
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
            {% if has_prev or has_more %}
            <div class="pagination">
                {% if has_prev %}
                    <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page - 1 }}">&laquo; Previous</a>
                {% endif %}
                <span class="current">Page {{ page }}</span>
                {% if has_more %}
                    <a href="/search?q={{ query | urlencode }}&sort={{ sort }}&page={{ page + 1 }}">Next &raquo;</a>
                {% endif %}
            </div>
            {% endif %}
        {% else %}
            <div class="no-results">No results found for "{{ query }}"</div>
        {% endif %}
    {% else %}
        <div class="no-results">Enter a search query to find emails</div>
    {% endif %}
{% endblock %}"""
    )
    HELP_TEMPLATE = BASE_TEMPLATE.replace(
        "{% block title %}ownmail{% endblock %}",
        "{% block title %}Search Help - ownmail{% endblock %}"
    ).replace(
        "{% block content %}{% endblock %}",
        """{% block content %}
    <div class="help-page">
        <h2>Search Syntax</h2>

        <h3>Field Filters</h3>
        <table class="help-table">
            <tr><td><code>from:user@example.com</code></td><td>Emails from this address</td></tr>
            <tr><td><code>to:user@example.com</code></td><td>Emails to this address</td></tr>
            <tr><td><code>subject:meeting</code></td><td>Emails with "meeting" in subject</td></tr>
            <tr><td><code>attachment:pdf</code></td><td>Emails with PDF attachments</td></tr>
            <tr><td><code>label:INBOX</code></td><td>Emails with specific Gmail label</td></tr>
        </table>

        <h3>Date Filters</h3>
        <table class="help-table">
            <tr><td><code>after:2024-01-15</code></td><td>Emails after this date</td></tr>
            <tr><td><code>before:2024-06-01</code></td><td>Emails before this date</td></tr>
            <tr><td><code>after:2024-01 before:2024-02</code></td><td>Emails in January 2024</td></tr>
        </table>

        <h3>Boolean Operators</h3>
        <table class="help-table">
            <tr><td><code>apple orange</code></td><td>Both words (implicit AND)</td></tr>
            <tr><td><code>apple OR orange</code></td><td>Either word</td></tr>
            <tr><td><code>apple NOT orange</code></td><td>Apple but not orange</td></tr>
            <tr><td><code>-orange</code></td><td>Exclude word (same as NOT)</td></tr>
        </table>

        <h3>Phrases &amp; Grouping</h3>
        <table class="help-table">
            <tr><td><code>"hello world"</code></td><td>Exact phrase</td></tr>
            <tr><td><code>(apple OR orange) juice</code></td><td>Grouping with parentheses</td></tr>
        </table>

        <h3>Prefix Matching</h3>
        <table class="help-table">
            <tr><td><code>meet*</code></td><td>Words starting with "meet" (meeting, meets, etc.)</td></tr>
        </table>

        <h3>Examples</h3>
        <table class="help-table">
            <tr><td><code>from:amazon invoice</code></td><td>Invoices from Amazon</td></tr>
            <tr><td><code>subject:urgent after:2024-01-01</code></td><td>Urgent emails this year</td></tr>
            <tr><td><code>attachment:pdf report OR invoice</code></td><td>PDFs with report or invoice</td></tr>
            <tr><td><code>label:IMPORTANT from:boss@work.com</code></td><td>Important emails from boss</td></tr>
        </table>

        <p><a href="/">&larr; Back to search</a></p>
    </div>
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
                <span class="email-header-label">From:</span>
                {% if sender_name and sender_email %}
                    {{ sender_name }}
                    &lt;<a href="/search?q=from:{{ sender_email | urlencode }}&sort=date_desc" class="clickable-header">{{ sender_email }}</a>&gt;
                {% elif sender_email %}
                    <a href="/search?q=from:{{ sender_email | urlencode }}&sort=date_desc" class="clickable-header">{{ sender_email }}</a>
                {% else %}
                    {{ sender }}
                {% endif %}
            </div>
            <div class="email-header-row">
                <span class="email-header-label">To:</span>
                {% for rcpt in recipients_parsed %}
                    {% if not loop.first %}, {% endif %}
                    {% if rcpt.name and rcpt.email %}
                        {{ rcpt.name }}
                        &lt;<a href="/search?q=to:{{ rcpt.email | urlencode }}&sort=date_desc" class="clickable-header">{{ rcpt.email }}</a>&gt;
                    {% elif rcpt.email %}
                        <a href="/search?q=to:{{ rcpt.email | urlencode }}&sort=date_desc" class="clickable-header">{{ rcpt.email }}</a>
                    {% else %}
                        {{ rcpt.raw }}
                    {% endif %}
                {% endfor %}
            </div>
            <div class="email-header-row">
                <span class="email-header-label">Date:</span> {{ date }}
            </div>
            {% if labels %}
            <div class="labels">
                {% for label in labels %}
                <a href="/search?q=label:{{ label | urlencode }}&sort=date_desc" class="label clickable-label">{{ label }}</a>
                {% endfor %}
            </div>
            {% endif %}
        </div>

        {% if images_blocked and has_external_images %}
        <div class="image-banner" id="image-banner">
            <span>🖼️ External images are blocked for security.</span>
            <button onclick="loadImages()">Load Images</button>
        </div>
        <script>
        function loadImages() {
            var iframe = document.getElementById('email-frame');
            if (iframe) {
                var doc = iframe.contentDocument;
                doc.querySelectorAll('img[data-src]').forEach(function(img) {
                    img.src = img.getAttribute('data-src');
                    img.removeAttribute('data-src');
                });
                // Resize after images load
                setTimeout(function() {
                    iframe.style.height = doc.body.scrollHeight + 20 + 'px';
                }, 500);
            }
            document.getElementById('image-banner').style.display = 'none';
        }
        </script>
        {% endif %}

        {% if body_html %}
            <iframe id="email-frame" class="email-body-html" sandbox="allow-same-origin" srcdoc="{{ body_html | e }}"></iframe>
            <script>
            // Auto-resize iframe to fit content
            document.getElementById('email-frame').onload = function() {
                try {
                    this.style.height = this.contentDocument.body.scrollHeight + 20 + 'px';
                } catch(e) {}
            };
            </script>
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
        stats = get_cached_stats()
        return render_template_string(SEARCH_TEMPLATE, stats=stats, query="", results=None, sort="relevance")

    @app.route("/help")
    def help_page():
        stats = get_cached_stats()
        return render_template_string(HELP_TEMPLATE, stats=stats)

    @app.route("/search")
    def search():
        query = request.args.get("q", "").strip()
        page = request.args.get("page", 1, type=int)
        sort = request.args.get("sort", "relevance")
        if sort not in ("relevance", "date_desc", "date_asc"):
            sort = "relevance"
        per_page = page_size  # Use configured page_size
        stats = get_cached_stats()

        if not query:
            return render_template_string(SEARCH_TEMPLATE, stats=stats, query="", results=None, sort=sort)

        # Server-side pagination: fetch only what we need + 1 to check if more exist
        offset = (page - 1) * per_page
        cache_key = f"{query}:{sort}:{offset}:{per_page}"

        # Check cache first
        cached = search_cache.get(cache_key)
        if cached is not None:
            if verbose:
                print(f"[verbose] Search cache HIT for: {query} (page {page}, sort {sort})", flush=True)
            raw_results = cached
        else:
            if verbose:
                print(f"[verbose] Searching for: {query} (page {page}, offset {offset}, sort {sort})", flush=True)
                start = time.time()

            # Fetch per_page + 1 to know if there are more results
            raw_results = archive.search(query, limit=per_page + 1, offset=offset, sort=sort)
            if verbose:
                print(f"[verbose] Search took {time.time()-start:.2f}s, {len(raw_results)} results", flush=True)

            # Cache the results
            search_cache.set(cache_key, raw_results)

        # Check if there are more results
        has_more = len(raw_results) > per_page
        if has_more:
            raw_results = raw_results[:per_page]

        # Format results - if subject/sender are empty, extract from email file
        results = []
        for msg_id, filename, subject, sender, date_str, snippet in raw_results:
            # For date-sorted queries, subject/sender/snippet may be empty - extract from file
            if not subject and filename:
                filepath = archive.archive_dir / filename
                if filepath.exists():
                    try:
                        with open(filepath, "rb") as f:
                            # Read enough for headers + start of body
                            content = f.read(32768)  # 32KB
                        msg = email.message_from_bytes(content)
                        subject = decode_header(msg.get("Subject", "")) or "(No subject)"
                        sender = decode_header(msg.get("From", ""))
                        date_str = msg.get("Date", "")

                        # Extract snippet from body if not provided
                        if not snippet:
                            snippet = _extract_snippet(msg)
                    except Exception:
                        subject = "(Error reading email)"
                        sender = ""

            results.append({
                "message_id": msg_id,
                "filename": filename,
                "subject": subject,
                "sender": sender,
                "date_str": date_str,
                "snippet": snippet,
            })

        return render_template_string(
            SEARCH_TEMPLATE,
            stats=stats,
            query=query,
            results=results,
            page=page,
            sort=sort,
            start_idx=offset,
            has_more=has_more,
            has_prev=page > 1,
        )

    @app.route("/email/<message_id>")
    def view_email(message_id: str):
        stats = get_cached_stats()

        # Check email cache first
        cached = email_cache.get(message_id)
        if cached is not None:
            if verbose:
                print(f"[verbose] Email cache HIT for: {message_id}", flush=True)
            email_data = cached
        else:
            # Get email file path from database
            if verbose:
                print(f"[verbose] Looking up email {message_id}...", flush=True)
                start = time.time()
            email_info = archive.db.get_email_by_id(message_id)
            if verbose:
                print(f"[verbose] DB lookup took {time.time()-start:.2f}s", flush=True)
            if not email_info:
                abort(404)

            filename = email_info[1]  # filename is second column
            filepath = archive.archive_dir / filename

            if not filepath.exists():
                abort(404)

            # Parse email
            if verbose:
                start = time.time()
            with open(filepath, "rb") as f:
                msg = email.message_from_binary_file(f)

            # Decode MIME-encoded headers
            subject = decode_header(msg.get("Subject", "")) or "(No subject)"
            sender = decode_header(msg.get("From", ""))
            recipients = decode_header(msg.get("To", ""))
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
                        att_filename = part.get_filename() or "attachment"
                        size = len(part.get_payload(decode=True) or b"")
                        attachments.append({
                            "filename": att_filename,
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
                    content_type = msg.get_content_type()
                    try:
                        decoded = payload.decode(charset, errors="replace")
                    except Exception:
                        decoded = payload.decode("utf-8", errors="replace")
                    if content_type == "text/html":
                        body_html = decoded
                    else:
                        body = decoded

            # Prefer HTML over plain text for better formatting
            # (we already block external images for privacy)
            if body_html:
                body = ""

            if verbose:
                print(f"[verbose] Email parsing took {time.time()-start:.2f}s", flush=True)

            # Cache the parsed email data
            email_data = {
                "subject": subject,
                "sender": sender,
                "recipients": recipients,
                "date": date,
                "labels": labels,
                "body": body,
                "body_html": body_html,
                "attachments": attachments,
            }
            email_cache.set(message_id, email_data)

        # Block external images if configured (do this after cache since it depends on config)
        body_html = email_data.get("body_html")
        has_external_images = False
        images_blocked = block_images
        if body_html and block_images:
            body_html, has_external_images = block_external_images(body_html)

        # Parse sender and recipients for clickable links
        sender_name, sender_email = parse_email_address(email_data["sender"])
        recipients_parsed = parse_recipients(email_data["recipients"])

        return render_template_string(
            EMAIL_TEMPLATE,
            stats=stats,
            message_id=message_id,
            subject=email_data["subject"],
            sender=email_data["sender"],
            sender_name=sender_name,
            sender_email=sender_email,
            recipients=email_data["recipients"],
            recipients_parsed=recipients_parsed,
            date=email_data["date"],
            labels=email_data["labels"],
            body=email_data["body"],
            body_html=body_html,
            attachments=email_data["attachments"],
            images_blocked=images_blocked,
            has_external_images=has_external_images,
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
    verbose: bool = False,
    block_images: bool = False,
    page_size: int = 20,
) -> None:
    """Run the web server.

    Args:
        archive: EmailArchive instance
        host: Host to bind to
        port: Port to listen on
        debug: Enable debug mode
        verbose: Enable request timing logs
        block_images: Block external images by default
        page_size: Number of results per page
    """
    app = create_app(archive, verbose=verbose, block_images=block_images, page_size=page_size)

    print("\n🌐 ownmail web interface")
    print(f"   Running at: http://{host}:{port}")
    print(f"   Page size: {page_size}")
    if verbose:
        print("   Verbose logging enabled")
    if block_images:
        print("   External images blocked by default")
    print("   Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=debug)
