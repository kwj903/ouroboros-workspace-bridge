#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNER = PROJECT_ROOT / "scripts" / "command_bundle_runner.py"

RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"
COMMAND_BUNDLES_DIR = RUNTIME_ROOT / "command_bundles"
PENDING_DIR = COMMAND_BUNDLES_DIR / "pending"
APPLIED_DIR = COMMAND_BUNDLES_DIR / "applied"
REJECTED_DIR = COMMAND_BUNDLES_DIR / "rejected"
FAILED_DIR = COMMAND_BUNDLES_DIR / "failed"

HOST = os.environ.get("BUNDLE_REVIEW_HOST", "127.0.0.1")
PORT = int(os.environ.get("BUNDLE_REVIEW_PORT", "8790"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bundle_dirs() -> list[Path]:
    return [PENDING_DIR, APPLIED_DIR, REJECTED_DIR, FAILED_DIR]


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_bundle(bundle_id: str) -> tuple[Path, dict[str, object]]:
    for directory in bundle_dirs():
        path = directory / f"{bundle_id}.json"
        if path.exists():
            return path, read_json(path)
    raise FileNotFoundError(f"Bundle not found: {bundle_id}")


def list_bundles() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for directory in bundle_dirs():
        if not directory.exists():
            continue

        for path in directory.glob("cmd-*.json"):
            try:
                record = read_json(path)
            except Exception:
                continue
            record["_file"] = str(path)
            rows.append(record)

    rows.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return rows


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def status_label(value: object) -> str:
    mapping = {
        "pending": "승인 대기",
        "applied": "적용 완료",
        "failed": "실패",
        "rejected": "거절됨",
        "unknown": "알 수 없음",
    }
    return mapping.get(str(value), str(value))


def risk_label(value: object) -> str:
    mapping = {
        "low": "낮음",
        "medium": "주의 필요",
        "high": "높음",
        "blocked": "차단됨",
        "unknown": "알 수 없음",
    }
    return mapping.get(str(value), str(value))


def bool_label(value: object) -> str:
    return "예" if bool(value) else "아니오"


def page(title: str, body: str) -> bytes:
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      max-width: 960px;
      margin: 32px auto;
      padding: 0 20px;
      line-height: 1.5;
    }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .card {{
      border: 1px solid #d0d7de;
      border-radius: 12px;
      padding: 16px;
      margin: 16px 0;
    }}
    .meta {{
      color: #667085;
      font-size: 14px;
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    pre {{
      background: rgba(127, 127, 127, 0.12);
      border-radius: 8px;
      padding: 12px;
      overflow-x: auto;
    }}
    button {{
      font-size: 16px;
      padding: 10px 14px;
      border-radius: 8px;
      border: 1px solid #888;
      cursor: pointer;
      margin-right: 8px;
    }}
    .approve {{ background: #16a34a; color: white; border-color: #16a34a; }}
    .reject {{ background: #dc2626; color: white; border-color: #dc2626; }}
    .pending {{ color: #ca8a04; font-weight: 700; }}
    .applied {{ color: #16a34a; font-weight: 700; }}
    .failed, .rejected {{ color: #dc2626; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  {body}
</body>
</html>
"""
    return html_text.encode("utf-8")


def run_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=300,
        shell=False,
        check=False,
    )


def step_text_meta_html(step: dict[str, object], key: str, label: str) -> str:
    ref_value = step.get(f"{key}_ref")
    chars_value = step.get(f"{key}_chars")
    chunks_value = step.get(f"{key}_chunks")

    if ref_value:
        return (
            f'<p class="meta">{escape(label)} ref: '
            f'<code>{escape(ref_value)}</code>, '
            f'길이: {escape(chars_value)}자, '
            f'청크: {escape(chunks_value)}</p>'
        )

    return f'<p class="meta">{escape(label)} 길이: {len(str(step.get(key, "")))}자</p>'


def step_summary_html(step: dict[str, object], idx: int) -> str:
    kind = str(step.get("type", "command"))

    if kind == "command":
        detail = f"""
        <p class="meta">명령:</p>
        <pre>{escape(step.get("argv", []))}</pre>
        <p class="meta">제한 시간: {escape(step.get("timeout_seconds", ""))}</p>
        """
    elif kind in {"write_file", "append_file"}:
        detail = f"""
        <p class="meta">파일: <code>{escape(step.get("path", ""))}</code></p>
        {step_text_meta_html(step, "content", "내용")}
        <p class="meta">덮어쓰기: {escape(bool_label(step.get("overwrite", False)))}</p>
        """
    elif kind == "replace_text":
        detail = f"""
        <p class="meta">파일: <code>{escape(step.get("path", ""))}</code></p>
        {step_text_meta_html(step, "old_text", "기존 문구")}
        {step_text_meta_html(step, "new_text", "새 문구")}
        <p class="meta">전체 치환: {escape(bool_label(step.get("replace_all", False)))}</p>
        """
    elif kind == "apply_patch":
        detail = f"""
        <p class="meta">작업 위치: <code>{escape(step.get("cwd", ""))}</code></p>
        {step_text_meta_html(step, "patch", "Patch")}
        <p class="meta">대상 파일:</p>
        <pre>{escape(json.dumps(step.get("files", []), ensure_ascii=False, indent=2))}</pre>
        <p class="meta">Patch sha256: <code>{escape(step.get("patch_sha256", ""))}</code></p>
        """
    else:
        detail = f"<pre>{escape(step)}</pre>"

    return f"""
    <div class="card">
      <h3>{idx}. {escape(step.get("name", ""))}</h3>
      <p class="meta">작업 종류: <code>{escape(kind)}</code></p>
      <p class="meta">위험도: <code>{escape(risk_label(step.get("risk", "")))}</code></p>
      <p class="meta">이유: {escape(step.get("reason", ""))}</p>
      {detail}
    </div>
    """


def bundle_summary_html(record: dict[str, object]) -> str:
    steps = record.get("steps")
    if not isinstance(steps, list):
        steps = []

    step_items: list[str] = []
    for idx, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        step_items.append(step_summary_html(step, idx))

    return "\n".join(step_items)


class Handler(BaseHTTPRequestHandler):
    server_version = "CommandBundleReview/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[review-ui] {self.address_string()} - {fmt % args}")

    def send_html(self, title: str, body: str, status: int = 200) -> None:
        payload = page(title, body)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parsed.path in {"/", "/bundles"}:
            rows = list_bundles()
            cards = []
            for record in rows:
                bundle_id = str(record.get("bundle_id", ""))
                status = str(record.get("status", "unknown"))
                cards.append(
                    f"""
                    <div class="card">
                      <h2><a href="/bundles/{escape(bundle_id)}">{escape(record.get("title", ""))}</a></h2>
                      <p class="meta">
                        ID: <code>{escape(bundle_id)}</code><br>
                        작업 위치: <code>{escape(record.get("cwd", ""))}</code><br>
                        상태: <span class="{escape(status)}">{escape(status_label(status))}</span><br>
                        위험도: <code>{escape(risk_label(record.get("risk", "")))}</code><br>
                        수정: {escape(record.get("updated_at", ""))}
                      </p>
                    </div>
                    """
                )

            self.send_html(
                "명령 번들 목록",
                "<p><a href='/bundles'>새로고침</a></p>" + "\n".join(cards) if cards else "<p>번들이 없습니다.</p>",
            )
            return

        if len(parts) == 2 and parts[0] == "bundles":
            bundle_id = parts[1]
            try:
                path, record = find_bundle(bundle_id)
            except FileNotFoundError as exc:
                self.send_html("찾을 수 없음", f"<pre>{escape(exc)}</pre>", status=404)
                return

            status = str(record.get("status", "unknown"))
            result = record.get("result")
            error = record.get("error")

            controls = ""
            if status == "pending":
                controls = f"""
                <form method="post" action="/bundles/{escape(bundle_id)}/approve" style="display:inline">
                  <button class="approve" type="submit">승인하고 실행</button>
                </form>
                <form method="post" action="/bundles/{escape(bundle_id)}/reject" style="display:inline">
                  <button class="reject" type="submit">거절</button>
                </form>
                """

            result_block = ""
            if result is not None:
                result_block = f"<h2>실행 결과</h2><pre>{escape(json.dumps(result, ensure_ascii=False, indent=2))}</pre>"
            if error:
                result_block += f"<h2>오류</h2><pre>{escape(error)}</pre>"

            body = f"""
            <p><a href="/bundles">← 목록으로 돌아가기</a></p>
            <div class="card">
              <p class="meta">
                ID: <code>{escape(bundle_id)}</code><br>
                작업 위치: <code>{escape(record.get("cwd", ""))}</code><br>
                상태: <span class="{escape(status)}">{escape(status_label(status))}</span><br>
                위험도: <code>{escape(risk_label(record.get("risk", "")))}</code><br>
                승인 필요: <code>{escape(bool_label(record.get("approval_required", False)))}</code><br>
                생성: {escape(record.get("created_at", ""))}<br>
                수정: {escape(record.get("updated_at", ""))}<br>
                파일: <code>{escape(path)}</code>
              </p>
              {controls}
            </div>
            <h2>실행 단계</h2>
            {bundle_summary_html(record)}
            {result_block}
            """
            self.send_html(str(record.get("title", bundle_id)), body)
            return

        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "ts": now_iso()}).encode("utf-8"))
            return

        self.send_html("찾을 수 없음", "<p>찾을 수 없습니다.</p>", status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) == 3 and parts[0] == "bundles" and parts[2] in {"approve", "reject"}:
            bundle_id = parts[1]
            action = parts[2]

            if action == "approve":
                completed = run_runner(["apply", bundle_id, "--yes"])
            else:
                completed = run_runner(["reject", bundle_id])

            output = {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }

            if completed.returncode != 0:
                body = f"""
                <p><a href="/bundles/{escape(bundle_id)}">← Back</a></p>
                <h2>실행기 오류</h2>
                <pre>{escape(json.dumps(output, ensure_ascii=False, indent=2))}</pre>
                """
                self.send_html("실행기 오류", body, status=500)
                return

            self.redirect(f"/bundles/{bundle_id}")
            return

        self.send_html("찾을 수 없음", "<p>찾을 수 없습니다.</p>", status=404)


def main() -> None:
    for directory in bundle_dirs():
        directory.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/bundles"
    print(f"명령 번들 승인 UI 실행 중: {url}")
    print("종료하려면 Ctrl-C를 누르세요.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n승인 UI를 종료합니다...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
