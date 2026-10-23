import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _build_html() -> str:
    copy_snippet = "copy(localStorage.getItem('Abp.AuthToken'))"

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Raksa - Huoneistotieto Auth Setup</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #1a1a2e;
      color: #e0e0e0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }}
    .card {{
      background: #16213e;
      border: 1px solid #0f3460;
      border-radius: 12px;
      padding: 2rem;
      max-width: 640px;
      width: 100%;
    }}
    h1 {{
      font-size: 1.4rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
      color: #fff;
    }}
    .step-label {{
      color: #4da6ff;
      font-weight: 600;
      font-size: 0.9rem;
      margin-bottom: 0.5rem;
    }}
    p {{
      color: #a0a0b0;
      line-height: 1.6;
      margin-bottom: 1.25rem;
    }}
    a {{ color: #4da6ff; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .code-block {{
      background: #0d1b2a;
      border: 1px solid #1e3a5f;
      border-radius: 8px;
      padding: 1rem;
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }}
    .code-block code {{
      font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
      font-size: 0.82rem;
      color: #7dd3fc;
      flex: 1;
      word-break: break-all;
      white-space: pre-wrap;
      line-height: 1.5;
    }}
    .btn {{
      cursor: pointer;
      border: none;
      border-radius: 6px;
      padding: 0.45rem 0.85rem;
      font-size: 0.82rem;
      font-weight: 500;
      transition: background 0.15s;
    }}
    .btn-copy {{
      background: #1e3a5f;
      color: #7dd3fc;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .btn-copy:hover {{ background: #254d7a; }}
    .btn-primary {{
      background: #4da6ff;
      color: #fff;
      padding: 0.6rem 1.25rem;
      font-size: 0.9rem;
      width: 100%;
    }}
    .btn-primary:hover {{ background: #3a8fe8; }}
    .section {{
      margin-bottom: 1.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid #2a2a4a;
    }}
    .section:last-of-type {{
      border-bottom: none;
      margin-bottom: 0;
      padding-bottom: 0;
    }}
    textarea {{
      width: 100%;
      background: #0d1b2a;
      border: 1px solid #1e3a5f;
      border-radius: 8px;
      color: #e0e0e0;
      font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
      font-size: 0.82rem;
      padding: 0.75rem;
      resize: vertical;
      min-height: 60px;
      margin-bottom: 0.75rem;
      outline: none;
    }}
    textarea:focus {{ border-color: #4da6ff; }}
    .success {{
      display: none;
      text-align: center;
      padding: 1.5rem 0;
    }}
    .success .checkmark {{ font-size: 2.5rem; margin-bottom: 0.75rem; color: #4ade80; }}
    .success h2 {{ font-size: 1.2rem; color: #4ade80; margin-bottom: 0.5rem; }}
    .success p {{ margin: 0; font-size: 0.9rem; }}
    .error-msg {{
      color: #f87171;
      font-size: 0.82rem;
      margin-top: 0.4rem;
      display: none;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div id="form-content">
      <h1>Huoneistotieto Auth Setup</h1>
      <p>Extract your token from huoneistotieto.fi in two steps.</p>

      <div class="section">
        <div class="step-label">Step 1 &mdash; Copy token from Huoneistotieto</div>
        <p>Open <a href="https://huoneistotieto.fi" target="_blank">huoneistotieto.fi</a>,
           log in, press F12, go to Console, and paste this snippet:</p>
        <div class="code-block">
          <code id="snippet">{snippet}</code>
          <button class="btn btn-copy" onclick="copySnippet()">Copy</button>
        </div>
        <p style="margin-bottom:0">This copies your auth token to the clipboard.</p>
      </div>

      <div class="section">
        <div class="step-label">Step 2 &mdash; Paste it here</div>
        <textarea id="manual-input" placeholder='Paste the token here'></textarea>
        <div class="error-msg" id="error-msg"></div>
        <button class="btn btn-primary" onclick="saveToken()">Save</button>
      </div>
    </div>
    <div class="success" id="success">
      <div class="checkmark">&#10003;</div>
      <h2>Token saved!</h2>
      <p>You can close this tab. The CLI will continue automatically.</p>
    </div>
  </div>

  <script>
    function copySnippet() {{
      const text = document.getElementById('snippet').textContent;
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.querySelector('.btn-copy');
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 1500);
      }});
    }}

    function showSuccess() {{
      document.getElementById('form-content').style.display = 'none';
      document.getElementById('success').style.display = 'block';
    }}

    function showError(msg) {{
      const el = document.getElementById('error-msg');
      el.textContent = msg;
      el.style.display = 'block';
    }}

    function saveToken() {{
      const raw = document.getElementById('manual-input').value.trim();
      if (!raw) {{
        showError('Paste the token from step 1 first.');
        return;
      }}
      // Basic JWT format check (three dot-separated base64 segments)
      if (raw.split('.').length !== 3) {{
        showError('That does not look like a valid JWT token. Make sure you copied the full token.');
        return;
      }}
      document.getElementById('error-msg').style.display = 'none';
      fetch('/token', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{token: raw}})
      }}).then(r => {{
        if (r.ok) showSuccess();
        else r.text().then(t => showError('Server error: ' + t));
      }}).catch(e => showError('Request failed: ' + e));
    }}
  </script>
</body>
</html>""".format(snippet=copy_snippet)


def run_ht_auth_server() -> str | None:
    port = _find_free_port()
    result: dict = {}
    shutdown_event = threading.Event()

    html = _build_html()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            pass

        def _send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

        def do_OPTIONS(self):
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self):
            if self.path != "/":
                self.send_response(404)
                self.end_headers()
                return
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/token":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b"Invalid JSON")
                return

            token = data.get("token")
            if not token:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b"Missing token")
                return

            result["token"] = token

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

            threading.Timer(1.0, shutdown_event.set).start()

    server = HTTPServer(("localhost", port), Handler)
    server.timeout = 1.0

    webbrowser.open(f"http://localhost:{port}")

    while not shutdown_event.is_set():
        server.handle_request()

    server.server_close()

    if result:
        return result["token"]
    return None
