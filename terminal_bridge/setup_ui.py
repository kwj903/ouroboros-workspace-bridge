from __future__ import annotations

import html
import http.client
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from terminal_bridge import session_supervisor as supervisor
from terminal_bridge.review_notifications import open_url


HOST = "127.0.0.1"
DEFAULT_PORT = 8791
MAX_PORT_ATTEMPTS = 10
REVIEW_REACHABLE_TIMEOUT_SECONDS = 0.5
GITHUB_DOC_KO = "https://github.com/kwj903/ouroboros-workspace-bridge/blob/main/docs/ko/chatgpt-app-setup.md"
GITHUB_DOC_EN = "https://github.com/kwj903/ouroboros-workspace-bridge/blob/main/docs/en/chatgpt-app-setup.md"
NGROK_DOWNLOADS_URL = "https://ngrok.com/downloads"


TEXT = {
    "ko": {
        "title": "Ouroboros Workspace Bridge 설정 마법사",
        "subtitle": "터미널 setup 흐름은 그대로 두고, 처음 설정을 브라우저에서 따라가기 위한 보조 화면입니다.",
        "language": "언어",
        "environment": "환경 확인",
        "ready": "준비됨",
        "needed": "필요함",
        "optional": "선택 사항",
        "python": "Python 실행",
        "uv": "uv",
        "ngrok": "ngrok CLI",
        "token": "MCP_ACCESS_TOKEN",
        "host": "NGROK_HOST",
        "workspace": "WORKSPACE_ROOT",
        "review": "review UI",
        "review_not_ready": "접속되지 않음. 터미널에서 `uv run woojae start`를 실행하세요.",
        "check_again": "다시 확인",
        "ngrok_title": "ngrok 준비",
        "ngrok_intro": "authtoken은 이 화면에 입력하지 않습니다. ngrok dashboard에서 복사한 뒤 터미널에서 직접 실행하세요.",
        "ngrok_downloads": "ngrok 공식 다운로드 페이지",
        "linux_fallback": "다른 Linux 배포판은 ngrok 공식 다운로드 페이지의 패키지 또는 zip 설치 방법을 참고하세요.",
        "windows_fallback": "winget이 없거나 Microsoft Store 사용이 막혀 있으면 ngrok 공식 다운로드 페이지에서 Windows용 zip을 받은 뒤 `ngrok.exe`를 PATH에 추가하세요.",
        "workspace_title": "Workspace 설정",
        "workspace_text": "WORKSPACE_ROOT는 ChatGPT가 읽고 proposal을 만들 수 있는 로컬 디렉토리입니다. 웹 저장은 다음 단계로 남겨두고, 변경은 터미널 setup에서 수행합니다.",
        "change_workspace": "바꾸려면 터미널에서 실행:",
        "connect_title": "ChatGPT 앱 연결",
        "connect_text": "실제 MCP URL에는 secret token이 포함되므로 이 화면에 표시하지 않습니다.",
        "local_docs": "로컬 checkout 문서 경로",
        "next_title": "다음 단계",
        "next_intro": "상태를 확인한 뒤 아래 순서대로 터미널 명령과 문서를 사용하세요.",
        "next_setup": "workspace, token, ngrok host 설정 확인",
        "next_start": "review/MCP/ngrok 세션 시작",
        "next_copy_url": "ChatGPT 앱에 넣을 실제 MCP URL 복사",
        "next_docs": "ChatGPT 앱 연결 문서 열기",
        "next_pending": "pending review UI 열기",
        "first_test": "첫 성공 테스트",
        "done": "설정 준비 완료",
        "done_title": "설정 준비가 완료되었습니다.",
        "done_body": "setup-ui 임시 서버를 종료합니다. 브라우저가 자동으로 닫히지 않으면 이 창은 닫아도 됩니다.",
        "copy": "복사",
        "copied": "복사됨",
        "docs_ko": "ChatGPT 앱 설정 문서",
        "docs_en": "English setup guide",
        "pending": "pending review UI 열기",
        "mcp_url": "`uv run woojae mcp-url`은 redacted preview만 보여줍니다.",
        "copy_url": "실제 URL은 `uv run woojae copy-url`로 clipboard에 복사하세요.",
        "prompt": "작업할 디렉토리는 /path/to/your/project 입니다.\n이 디렉토리의 구성을 간단히 보여주고, 어떤 종류의 프로젝트인지 요약해줘.",
    },
    "en": {
        "title": "Ouroboros Workspace Bridge setup wizard",
        "subtitle": "An optional browser onboarding helper. The terminal setup workflow remains the official default.",
        "language": "Language",
        "environment": "Environment check",
        "ready": "Ready",
        "needed": "Needed",
        "optional": "Optional",
        "python": "Python executable",
        "uv": "uv",
        "ngrok": "ngrok CLI",
        "token": "MCP_ACCESS_TOKEN",
        "host": "NGROK_HOST",
        "workspace": "WORKSPACE_ROOT",
        "review": "review UI",
        "review_not_ready": "Not reachable. Run `uv run woojae start` in your terminal.",
        "check_again": "Check again",
        "ngrok_title": "Prepare ngrok",
        "ngrok_intro": "Do not enter your authtoken in this page. Copy it from the ngrok dashboard and run the command in your terminal.",
        "ngrok_downloads": "official ngrok downloads page",
        "linux_fallback": "For other Linux distributions, use the package or zip instructions from the official ngrok downloads page.",
        "windows_fallback": "If winget or Microsoft Store is unavailable, download the Windows zip from the official ngrok downloads page and add `ngrok.exe` to PATH.",
        "workspace_title": "Workspace settings",
        "workspace_text": "WORKSPACE_ROOT is the local directory ChatGPT may inspect and create proposals for. Web saving is reserved for a later step; change it with the terminal setup flow.",
        "change_workspace": "To change it, run:",
        "connect_title": "Connect ChatGPT app",
        "connect_text": "The real MCP URL contains a secret token, so this page does not display it.",
        "local_docs": "Local checkout docs path",
        "next_title": "Next",
        "next_intro": "After checking the status, use these terminal commands and docs in order.",
        "next_setup": "Confirm workspace, token, and ngrok host settings",
        "next_start": "Start the review/MCP/ngrok session",
        "next_copy_url": "Copy the real MCP URL for the ChatGPT app",
        "next_docs": "Open the ChatGPT app connection guide",
        "next_pending": "Open the pending review UI",
        "first_test": "First success test",
        "done": "Setup is ready",
        "done_title": "Setup is ready.",
        "done_body": "The temporary setup-ui server is shutting down. If the browser does not close automatically, you can close this tab.",
        "copy": "Copy",
        "copied": "Copied",
        "docs_ko": "Korean setup guide",
        "docs_en": "ChatGPT app setup docs",
        "pending": "Open pending review UI",
        "mcp_url": "`uv run woojae mcp-url` shows only a redacted preview.",
        "copy_url": "Use `uv run woojae copy-url` to copy the real URL to your clipboard.",
        "prompt": "Use this workspace directory: /path/to/your/project\nShow me a brief overview of this directory's structure and tell me what kind of project it looks like.",
    },
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _lang_from_request(path: str, headers: object, saved: str = "auto") -> str:
    query = parse_qs(urlparse(path).query)
    requested = (query.get("lang") or [""])[0].lower()
    if requested in {"ko", "en"}:
        return requested
    if saved in {"ko", "en"}:
        return saved
    accept_language = ""
    try:
        accept_language = str(headers.get("Accept-Language", ""))  # type: ignore[attr-defined]
    except Exception:
        accept_language = ""
    if accept_language.lower().startswith("en"):
        return "en"
    return "ko"


def _status_chip(ok: bool, labels: dict[str, str], optional: bool = False) -> str:
    label = labels["ready"] if ok else labels["optional" if optional else "needed"]
    class_name = "ok" if ok else "optional" if optional else "needed"
    return f'<span class="chip {class_name}">{_escape(label)}</span>'


def _copy_block(command: str, labels: dict[str, str], language: str = "bash") -> str:
    escaped_command = _escape(command)
    return f"""
    <div class="copy-block">
      <pre><code class="language-{_escape(language)}">{escaped_command}</code></pre>
      <button type="button" data-copy="{escaped_command}">{_escape(labels["copy"])}</button>
    </div>
    """


def _review_ui_reachable(settings: supervisor.SessionSettings, timeout: float = REVIEW_REACHABLE_TIMEOUT_SECONDS) -> bool:
    connection: http.client.HTTPConnection | None = None
    try:
        host = "127.0.0.1" if settings.review_host == "0.0.0.0" else settings.review_host
        connection = http.client.HTTPConnection(host, settings.review_port, timeout=timeout)
        connection.request("GET", "/pending")
        response = connection.getresponse()
        response.read(512)
        return response.status < 500
    except Exception:
        return False
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _environment_rows(settings: supervisor.SessionSettings, labels: dict[str, str], *, review_reachable: bool) -> str:
    uv_path = shutil.which("uv")
    ngrok_path = shutil.which("ngrok")
    review_value = settings.review_dashboard_url if review_reachable else f"{settings.review_dashboard_url} - {labels['review_not_ready']}"
    rows = [
        (labels["python"], True, sys.executable, False),
        (labels["uv"], uv_path is not None, uv_path or "uv not found", False),
        (labels["ngrok"], ngrok_path is not None, ngrok_path or "ngrok not found", False),
        (labels["token"], bool(settings.mcp_access_token), "set" if settings.mcp_access_token else "not set", False),
        (labels["host"], bool(settings.ngrok_host), settings.ngrok_host or "temporary URL mode", True),
        (labels["workspace"], bool(settings.workspace_root), settings.workspace_root, False),
        (labels["review"], review_reachable, review_value, False),
    ]
    html_rows = []
    for name, ok, value, optional in rows:
        html_rows.append(
            "<tr>"
            f"<th>{_escape(name)}</th>"
            f"<td>{_status_chip(ok, labels, optional=optional)}</td>"
            f"<td><code>{_escape(value)}</code></td>"
            "</tr>"
        )
    return "\n".join(html_rows)


def _ngrok_commands(labels: dict[str, str]) -> str:
    linux = "\n".join(
        [
            "curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null",
            'echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list',
            "sudo apt update",
            "sudo apt install ngrok",
        ]
    )
    blocks = [
        f"<h3>macOS</h3>{_copy_block('brew install ngrok', labels, 'bash')}",
        f"<h3>Debian/Ubuntu Linux</h3>{_copy_block(linux, labels, 'bash')}"
        f'<p class="hint">{_escape(labels["linux_fallback"])} '
        f'<a href="{NGROK_DOWNLOADS_URL}">{_escape(labels["ngrok_downloads"])}</a>.</p>',
        f"<h3>Windows PowerShell</h3>{_copy_block('winget install ngrok -s msstore', labels, 'powershell')}"
        f'<p class="hint">{_escape(labels["windows_fallback"])} '
        f'<a href="{NGROK_DOWNLOADS_URL}">{_escape(labels["ngrok_downloads"])}</a>.</p>',
        f"<h3>Authtoken</h3>{_copy_block('ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>', labels, 'bash')}",
    ]
    return "\n".join(blocks)


def render_setup_page(settings: supervisor.SessionSettings, *, language: str) -> str:
    labels = TEXT[language]
    setup_url = f"/setup?lang={language}"
    prompt = labels["prompt"]
    review_reachable = _review_ui_reachable(settings)
    return f"""<!doctype html>
<html lang="{_escape(language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(labels["title"])}</title>
  <style>
    :root {{ color-scheme: light dark; --ok: #147a3c; --need: #a33a19; --opt: #76620f; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; line-height: 1.5; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    h2 {{ margin-top: 32px; border-top: 1px solid #d0d7de; padding-top: 24px; }}
    .lang a, button, .link-button {{ border: 1px solid #8c959f; border-radius: 6px; padding: 7px 10px; background: transparent; color: inherit; text-decoration: none; cursor: pointer; }}
    .lang a.active {{ font-weight: 700; border-color: currentColor; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #d0d7de; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ width: 190px; }}
    code {{ word-break: break-word; }}
    pre {{ margin: 0; overflow: auto; }}
    .chip {{ display: inline-block; border-radius: 999px; padding: 2px 9px; font-size: 0.88rem; border: 1px solid currentColor; }}
    .chip.ok {{ color: var(--ok); }}
    .chip.needed {{ color: var(--need); }}
    .chip.optional {{ color: var(--opt); }}
    .copy-block {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: start; border: 1px solid #d0d7de; border-radius: 8px; padding: 10px; margin: 8px 0 16px; }}
    .notice {{ border-left: 4px solid #3778c2; padding: 10px 12px; background: rgba(55, 120, 194, 0.08); }}
    .hint, .muted {{ color: #57606a; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>{_escape(labels["title"])}</h1>
      <p>{_escape(labels["subtitle"])}</p>
    </div>
    <nav class="lang" aria-label="{_escape(labels["language"])}">
      <a class="{'active' if language == 'ko' else ''}" href="/setup?lang=ko">한국어</a>
      <a class="{'active' if language == 'en' else ''}" href="/setup?lang=en">English</a>
    </nav>
  </header>

  <section>
    <h2>{_escape(labels["environment"])}</h2>
    <div class="actions"><a class="link-button" href="{_escape(setup_url)}">{_escape(labels["check_again"])}</a></div>
    <table>{_environment_rows(settings, labels, review_reachable=review_reachable)}</table>
  </section>

  <section>
    <h2>{_escape(labels["ngrok_title"])}</h2>
    <p class="notice">{_escape(labels["ngrok_intro"])}</p>
    {_ngrok_commands(labels)}
  </section>

  <section>
    <h2>{_escape(labels["workspace_title"])}</h2>
    <p>{_escape(labels["workspace_text"])}</p>
    <p><strong>WORKSPACE_ROOT:</strong> <code>{_escape(settings.workspace_root)}</code></p>
    <p>{_escape(labels["change_workspace"])}</p>
    {_copy_block("uv run woojae setup", labels)}
  </section>

  <section>
    <h2>{_escape(labels["connect_title"])}</h2>
    <p>{_escape(labels["connect_text"])}</p>
    <ul>
      <li>{_escape(labels["mcp_url"])}</li>
      <li>{_escape(labels["copy_url"])}</li>
      <li><a href="{GITHUB_DOC_KO}">{_escape(labels["docs_ko"])}</a></li>
      <li><a href="{GITHUB_DOC_EN}">{_escape(labels["docs_en"])}</a></li>
      <li><a href="{_escape(settings.review_dashboard_url)}">{_escape(labels["pending"])}</a></li>
    </ul>
    <p class="muted">{_escape(labels["local_docs"])}: <code>docs/ko/chatgpt-app-setup.md</code>, <code>docs/en/chatgpt-app-setup.md</code></p>
  </section>

  <section>
    <h2>{_escape(labels["next_title"])}</h2>
    <p>{_escape(labels["next_intro"])}</p>
    <ol>
      <li>{_escape(labels["next_setup"])}{_copy_block("uv run woojae setup", labels)}</li>
      <li>{_escape(labels["next_start"])}{_copy_block("uv run woojae start", labels)}</li>
      <li>{_escape(labels["next_copy_url"])}{_copy_block("uv run woojae copy-url", labels)}</li>
      <li><a href="{GITHUB_DOC_KO if language == 'ko' else GITHUB_DOC_EN}">{_escape(labels["next_docs"])}</a></li>
      <li><a href="{_escape(settings.review_dashboard_url)}">{_escape(labels["next_pending"])}</a></li>
    </ol>
  </section>

  <section>
    <h2>{_escape(labels["first_test"])}</h2>
    {_copy_block(prompt, labels)}
  </section>

  <section>
    <h2>{_escape(labels["done"])}</h2>
    <form method="post" action="/done?lang={_escape(language)}">
      <button type="submit">{_escape(labels["done"])}</button>
    </form>
  </section>
</main>
<script>
document.querySelectorAll("[data-copy]").forEach((button) => {{
  button.addEventListener("click", async () => {{
    const text = button.getAttribute("data-copy") || "";
    try {{
      await navigator.clipboard.writeText(text);
    }} catch (error) {{
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }}
    button.textContent = {json.dumps(labels["copied"])};
  }});
}});
</script>
</body>
</html>"""


def render_done_page(settings: supervisor.SessionSettings, *, language: str) -> str:
    labels = TEXT[language]
    return f"""<!doctype html>
<html lang="{_escape(language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(labels["done_title"])}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 48px 20px; line-height: 1.5; }}
  </style>
</head>
<body>
<main>
  <h1>{_escape(labels["done_title"])}</h1>
  <p>{_escape(labels["done_body"])}</p>
  <p><a href="{_escape(settings.review_dashboard_url)}">{_escape(labels["pending"])}</a></p>
</main>
<script>
setTimeout(() => {{
  try {{ window.close(); }} catch (error) {{}}
}}, 500);
</script>
</body>
</html>"""


def notify_done() -> None:
    try:
        if sys.platform == "darwin" and shutil.which("osascript"):
            subprocess.run(
                ["osascript", "-e", 'display notification "Setup is ready." with title "Ouroboros Workspace Bridge"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        elif sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", "Ouroboros Workspace Bridge", "Setup is ready."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        elif sys.platform.startswith("win"):
            executable = shutil.which("powershell") or shutil.which("pwsh")
            if executable:
                script = (
                    "$ErrorActionPreference = 'Stop'; "
                    "if (Get-Module -ListAvailable -Name BurntToast) { "
                    "Import-Module BurntToast; New-BurntToastNotification -Text 'Ouroboros Workspace Bridge', 'Setup is ready.' "
                    "}"
                )
                subprocess.run(
                    [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
    except Exception:
        return


class SetupUiServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], settings: supervisor.SessionSettings):
        super().__init__(server_address, handler_class)
        self.settings = settings


class SetupUiHandler(BaseHTTPRequestHandler):
    server: SetupUiServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"", "/"}:
            self.send_response(302)
            self.send_header("Location", "/setup")
            self.end_headers()
            return
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if parsed.path != "/setup":
            self._send_html("<h1>Not found</h1>", status=404)
            return
        settings = supervisor.load_settings()
        self.server.settings = settings
        language = _lang_from_request(self.path, self.headers, settings.help_language)
        self._send_html(render_setup_page(settings, language=language))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/done":
            self._send_html("<h1>Not found</h1>", status=404)
            return
        settings = supervisor.load_settings()
        self.server.settings = settings
        language = _lang_from_request(self.path, self.headers, settings.help_language)
        self._send_html(render_done_page(settings, language=language))
        notify_done()
        threading.Thread(target=self.server.shutdown, name="setup-ui-shutdown", daemon=True).start()


def _bind_server(settings: supervisor.SessionSettings, port: int) -> SetupUiServer:
    last_error: OSError | None = None
    for candidate in range(port, port + MAX_PORT_ATTEMPTS):
        try:
            return SetupUiServer((HOST, candidate), SetupUiHandler, settings)
        except OSError as exc:
            last_error = exc
            continue
    raise OSError(f"Could not bind setup-ui on {HOST}:{port}-{port + MAX_PORT_ATTEMPTS - 1}: {last_error}")


def run_setup_ui(*, port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    settings = supervisor.load_settings()
    try:
        server = _bind_server(settings, port)
    except OSError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    actual_port = int(server.server_address[1])
    url = f"http://{HOST}:{actual_port}/setup"
    if actual_port != port:
        print(f"[warn] Port {port} was unavailable; using {actual_port}.")
    print("Ouroboros Workspace Bridge setup UI")
    print(f"URL: {url}")
    print("This temporary localhost server exits when you click the setup completion button.")

    if open_browser:
        try:
            open_url(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("setup-ui interrupted.")
    finally:
        server.server_close()
    return 0
