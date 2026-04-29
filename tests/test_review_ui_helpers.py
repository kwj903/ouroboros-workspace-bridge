from __future__ import annotations

import inspect
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import server
from scripts import command_bundle_review_server as review
from scripts import command_bundle_watcher as watcher
from terminal_bridge import config, handoffs, safety, tool_calls
from terminal_bridge import review_intents as intents
from terminal_bridge import review_notifications as notifications


class ReviewServerHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        self.original_dirs = (
            review.PENDING_DIR,
            review.APPLIED_DIR,
            review.REJECTED_DIR,
            review.FAILED_DIR,
        )
        self.original_audit_log = review.AUDIT_LOG
        self.original_runtime_root = review.RUNTIME_ROOT
        self.original_handoff_dir = handoffs.HANDOFF_DIR

        review.PENDING_DIR = root / "pending"
        review.APPLIED_DIR = root / "applied"
        review.REJECTED_DIR = root / "rejected"
        review.FAILED_DIR = root / "failed"
        review.AUDIT_LOG = root / "audit.jsonl"
        handoffs.HANDOFF_DIR = root / "handoffs"

        for directory in review.bundle_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        (
            review.PENDING_DIR,
            review.APPLIED_DIR,
            review.REJECTED_DIR,
            review.FAILED_DIR,
        ) = self.original_dirs
        review.AUDIT_LOG = self.original_audit_log
        review.RUNTIME_ROOT = self.original_runtime_root
        handoffs.HANDOFF_DIR = self.original_handoff_dir
        self.tmp.cleanup()

    def write_bundle(self, status: str, bundle_id: str, updated_at: str) -> None:
        self.write_bundle_record(
            status,
            {
                "bundle_id": bundle_id,
                "title": bundle_id,
                "cwd": ".",
                "status": status,
                "risk": "medium",
                "updated_at": updated_at,
                "steps": [],
            },
        )

    def write_bundle_record(self, status: str, record: dict[str, object]) -> None:
        bundle_id = str(record["bundle_id"])
        path = getattr(review, f"{status.upper()}_DIR") / f"{bundle_id}.json"
        path.write_text(json.dumps(record), encoding="utf-8")

    def write_audit_lines(self, *items: object) -> None:
        lines = []
        for item in items:
            if isinstance(item, str):
                lines.append(item)
            else:
                lines.append(json.dumps(item, ensure_ascii=False))
        review.AUDIT_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_list_bundles_filters_by_status(self) -> None:
        self.write_bundle("pending", "cmd-pending", "2026-01-02T00:00:00+00:00")
        self.write_bundle("applied", "cmd-applied", "2026-01-01T00:00:00+00:00")

        self.assertEqual([item["bundle_id"] for item in review.list_bundles("pending")], ["cmd-pending"])
        self.assertEqual([item["bundle_id"] for item in review.list_bundles("applied")], ["cmd-applied"])
        self.assertEqual(len(review.list_bundles("all")), 2)

    def test_latest_pending_bundle_id_uses_newest_pending(self) -> None:
        self.write_bundle("pending", "cmd-old", "2026-01-01T00:00:00+00:00")
        self.write_bundle("pending", "cmd-new", "2026-01-02T00:00:00+00:00")

        self.assertEqual(review.latest_pending_bundle_id(), "cmd-new")

    def test_command_bundle_revision_changes_with_state(self) -> None:
        before = review.command_bundle_revision()
        self.write_bundle("pending", "cmd-revision", "2026-01-01T00:00:00+00:00")
        after = review.command_bundle_revision()

        self.assertNotEqual(before, after)

    def test_command_bundle_state_counts_pending(self) -> None:
        self.write_bundle("pending", "cmd-pending", "2026-01-02T00:00:00+00:00")
        self.write_bundle("failed", "cmd-failed", "2026-01-03T00:00:00+00:00")

        state = review.command_bundle_state()

        self.assertEqual(state["pending_count"], 1)
        self.assertEqual(state["latest_pending_bundle_id"], "cmd-pending")

    def test_current_pending_bundle_ids_reads_existing_pending(self) -> None:
        self.write_bundle("pending", "cmd-existing", "2026-01-02T00:00:00+00:00")

        self.assertEqual(review.current_pending_bundle_ids(), {"cmd-existing"})

    def test_bundle_status_counts(self) -> None:
        self.write_bundle("pending", "cmd-pending", "2026-01-01T00:00:00+00:00")
        self.write_bundle("applied", "cmd-applied", "2026-01-02T00:00:00+00:00")
        self.write_bundle("failed", "cmd-failed", "2026-01-03T00:00:00+00:00")
        self.write_bundle("rejected", "cmd-rejected", "2026-01-04T00:00:00+00:00")

        counts = review.bundle_status_counts()

        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["applied"], 1)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["all"], 4)

    def test_latest_bundle_id_and_updated_at(self) -> None:
        self.write_bundle("failed", "cmd-old-failed", "2026-01-01T00:00:00+00:00")
        self.write_bundle("failed", "cmd-new-failed", "2026-01-03T00:00:00+00:00")
        self.write_bundle("applied", "cmd-newest", "2026-01-04T00:00:00+00:00")

        self.assertEqual(review.latest_bundle_id("failed"), "cmd-new-failed")
        self.assertEqual(review.latest_updated_at(), "2026-01-04T00:00:00+00:00")

    def test_step_result_status(self) -> None:
        self.assertEqual(review.step_result_status({"exit_code": 0}), "success")
        self.assertEqual(review.step_result_status({"exit_code": 1}), "failed")
        self.assertEqual(review.step_result_status({}), "unknown")
        self.assertEqual(review.step_result_status({"exit_code": None}), "unknown")

    def test_summarize_bundle_result_counts_failed_steps(self) -> None:
        summary = review.summarize_bundle_result(
            {
                "steps": [{"name": "one"}, {"name": "two"}],
                "result": {
                    "steps": [
                        {"name": "one", "exit_code": 0},
                        {"name": "two", "exit_code": 2},
                        {"name": "three"},
                    ]
                },
                "error": "One or more bundle steps failed.",
            }
        )

        self.assertEqual(summary["command_count"], 2)
        self.assertEqual(summary["result_step_count"], 3)
        self.assertEqual(summary["failed_step_count"], 1)
        self.assertEqual(summary["error_summary"], "One or more bundle steps failed.")

    def test_copy_for_chatgpt_summary_for_applied_bundle(self) -> None:
        summary = review.copy_for_chatgpt_summary(
            {
                "bundle_id": "cmd-applied",
                "title": "Applied bundle",
                "status": "applied",
                "risk": "low",
                "result": {
                    "steps": [
                        {
                            "stdout": "line one\nline two",
                            "stderr": "",
                            "exit_code": 0,
                        }
                    ]
                },
            }
        )

        self.assertEqual(summary["bundle_id"], "cmd-applied")
        self.assertEqual(summary["status"], "applied")
        self.assertEqual(summary["title"], "Applied bundle")
        self.assertEqual(summary["risk"], "low")
        self.assertEqual(summary["ok"], True)
        self.assertEqual(summary["next"], "continue")
        self.assertIn("line two", summary["stdout_tail"])

    def test_bundle_detail_html_can_show_applied_bundle(self) -> None:
        self.write_bundle_record(
            "applied",
            {
                "bundle_id": "cmd-applied",
                "title": "Applied bundle",
                "cwd": ".",
                "status": "applied",
                "risk": "low",
                "approval_required": True,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:01:00+00:00",
                "steps": [{"name": "Git status", "type": "command", "risk": "low"}],
                "result": {"steps": [{"name": "Git status", "stdout": "## main", "exit_code": 0}]},
            },
        )

        path, record = review.find_bundle("cmd-applied")
        html = review.bundle_detail_html(path, record)

        self.assertIn("Copy for ChatGPT", html)
        self.assertIn("&quot;bundle_id&quot;: &quot;cmd-applied&quot;", html)
        self.assertIn("&quot;status&quot;: &quot;applied&quot;", html)
        self.assertIn("&quot;title&quot;: &quot;Applied bundle&quot;", html)
        self.assertIn("&quot;risk&quot;: &quot;low&quot;", html)
        self.assertIn("&quot;next&quot;: &quot;continue&quot;", html)
        self.assertIn("## main", html)

    def test_bundle_detail_html_keeps_pending_approval_controls(self) -> None:
        self.write_bundle_record(
            "pending",
            {
                "bundle_id": "cmd-pending",
                "title": "Pending bundle",
                "cwd": ".",
                "status": "pending",
                "risk": "medium",
                "approval_required": True,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:01:00+00:00",
                "steps": [],
            },
        )

        path, record = review.find_bundle("cmd-pending")
        html = review.bundle_detail_html(path, record)

        self.assertIn('/bundles/cmd-pending/approve', html)
        self.assertIn('/bundles/cmd-pending/reject', html)
        self.assertIn("&quot;status&quot;: &quot;pending&quot;", html)

    def test_intent_inbox_form_is_rendered_on_pending_page(self) -> None:
        html = review.intent_inbox_html()

        self.assertIn("<details", html)
        self.assertIn("고급: Intent 직접 가져오기", html)
        self.assertIn("일반 승인에는 필요 없습니다", html)
        self.assertIn('action="/intents/import"', html)
        self.assertIn('name="token"', html)
        self.assertIn("Import intent", html)

    def test_extract_intent_token_accepts_raw_token_and_full_url(self) -> None:
        raw = "abc.def"
        url = "http://127.0.0.1:8765/review-intent?token=abc.def"

        self.assertEqual(intents.extract_intent_token(raw), raw)
        self.assertEqual(intents.extract_intent_token(url), raw)

    def test_import_intent_token_accepts_raw_and_full_url_idempotently(self) -> None:
        original_secret_file = server.INTENT_SECRET_FILE
        original_import_dir = server.INTENT_IMPORT_DIR
        original_changed_paths = server._intent_changed_paths
        original_audit = server._audit
        original_tool_call_dir = tool_calls.TOOL_CALL_DIR
        bundle_ids: list[str] = []
        tmp = tempfile.TemporaryDirectory()
        try:
            root = Path(tmp.name)
            server.INTENT_SECRET_FILE = root / "intent_secret"
            server.INTENT_IMPORT_DIR = root / "intent_imports"
            tool_calls.TOOL_CALL_DIR = root / "tool_calls"
            server._intent_changed_paths = lambda cwd, include_untracked: ["README.md"]
            server._audit = lambda *args, **kwargs: None

            before_count = sum(
                1
                for directory in server._command_bundle_dirs()
                if directory.exists()
                for _ in directory.glob("cmd-*.json")
            )
            intent = server.workspace_prepare_commit_current_changes_intent(
                cwd=safety._relative(config.PROJECT_ROOT),
                message=f"Inbox intent import {uuid4().hex[:8]}",
                include_untracked=False,
            )
            token = str(intent["local_review_url"]).split("token=", 1)[1]

            first_bundle_id = intents.import_intent_token(token)
            second_bundle_id = intents.import_intent_token(str(intent["local_review_url"]))
            redirect_location = review.intent_import_redirect_location(token)
            after_count = sum(
                1
                for directory in server._command_bundle_dirs()
                if directory.exists()
                for _ in directory.glob("cmd-*.json")
            )
            bundle_ids.append(first_bundle_id)

            self.assertEqual(first_bundle_id, second_bundle_id)
            self.assertEqual(redirect_location, f"/pending?bundle_id={first_bundle_id}")
            self.assertEqual(after_count, before_count + 1)
        finally:
            server.INTENT_SECRET_FILE = original_secret_file
            server.INTENT_IMPORT_DIR = original_import_dir
            server._intent_changed_paths = original_changed_paths
            server._audit = original_audit
            tool_calls.TOOL_CALL_DIR = original_tool_call_dir
            for bundle_id in bundle_ids:
                for status in ("pending", "applied", "rejected", "failed"):
                    server._command_bundle_path(bundle_id, status).unlink(missing_ok=True)
            tmp.cleanup()

    def test_intent_import_result_rejects_json_payloads(self) -> None:
        payload = {
            "version": 1,
            "intent_type": "check",
            "cwd": safety._relative(config.PROJECT_ROOT),
            "params": {"check": "git_status"},
        }

        with self.assertRaises(ValueError):
            intents.intent_import_result(payload)

    def test_intent_import_error_html_is_clear(self) -> None:
        html = review.intent_import_error_html("ValueError: Intent token has expired.")

        self.assertIn("Intent import failed", html)
        self.assertIn("expired", html)
        self.assertIn("고급: Intent 직접 가져오기", html)

    def test_latest_handoff_html_links_to_focused_bundle(self) -> None:
        handoffs.write_handoff_from_bundle(
            {
                "bundle_id": "cmd-latest",
                "title": "Latest handoff",
                "cwd": ".",
                "status": "applied",
                "risk": "low",
                "result": {"ok": True, "steps": [{"stdout": "done", "stderr": "", "exit_code": 0}]},
                "error": None,
            }
        )

        html = review.latest_handoff_html()

        self.assertIn("Latest handoff / Copy for ChatGPT", html)
        self.assertIn("/pending?bundle_id=cmd-latest", html)
        self.assertIn("&quot;bundle_id&quot;: &quot;cmd-latest&quot;", html)

    def test_latest_handoff_payload_returns_latest_handoff_json(self) -> None:
        handoffs.write_handoff_from_bundle(
            {
                "bundle_id": "cmd-latest-json",
                "title": "Latest handoff JSON",
                "cwd": ".",
                "status": "applied",
                "risk": "low",
                "result": {"ok": True, "steps": [{"stdout": "done", "stderr": "", "exit_code": 0}]},
                "error": None,
            }
        )

        payload = review.latest_handoff_payload()

        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["handoff"]["bundle_id"], "cmd-latest-json")

    def test_docs_describe_bundle_tool_workflow(self) -> None:
        english = (config.PROJECT_ROOT / "docs/en/workflow.md").read_text(encoding="utf-8")
        korean = (config.PROJECT_ROOT / "docs/ko/workflow.md").read_text(encoding="utf-8")

        self.assertIn("workspace_submit_command_bundle", english)
        self.assertIn("local pending review UI", english)
        self.assertIn("browser companion", english.lower())
        self.assertIn("is discontinued", english)
        self.assertIn("workspace_recover_last_activity", english)
        self.assertIn("workspace_submit_command_bundle", korean)
        self.assertIn("local pending review UI", korean)
        self.assertIn("browser companion", korean.lower())
        self.assertIn("중단", korean)
        self.assertIn("workspace_recover_last_activity", korean)

    def test_short_error_truncates_long_strings(self) -> None:
        error = review.short_error("x" * 200, max_chars=20)

        self.assertLessEqual(len(error), 20)
        self.assertTrue(error.endswith("…"))

    def test_history_state_omits_token_values(self) -> None:
        original_token = os.environ.get("MCP_ACCESS_TOKEN")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            self.write_bundle("failed", "cmd-failed", "2026-01-03T00:00:00+00:00")
            serialized = json.dumps(review.history_state(), ensure_ascii=False)

            self.assertIn('"latest_failed_bundle_id": "cmd-failed"', serialized)
            self.assertNotIn("secret-token-value", serialized)
            self.assertNotIn("access_token", serialized)
        finally:
            if original_token is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original_token

    def test_audit_state_returns_empty_events_when_log_missing(self) -> None:
        state = review.audit_state()

        self.assertEqual(state["count"], 0)
        self.assertEqual(state["events"], [])

    def test_recent_audit_events_skips_broken_json_lines(self) -> None:
        self.write_audit_lines(
            '{"bad json"',
            {
                "ts": "2026-01-01T00:00:00+00:00",
                "event": "stage_action_bundle",
                "bundle_id": "cmd-good",
                "title": "Good bundle",
            },
        )

        state = review.audit_state()

        self.assertEqual(state["count"], 1)
        self.assertEqual(state["events"][0]["bundle_id"], "cmd-good")

    def test_audit_event_summary_html_escapes_values(self) -> None:
        html = review.audit_event_summary_html(
            {
                "bundle_id": "cmd-test",
                "title": "<script>alert(1)</script>",
                "cwd": ".",
            }
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_audit_command_summary_truncates_long_lists(self) -> None:
        summary = review.summarize_audit_command(["uv", "run", "python", "-m", "unittest", "discover", "-s"])

        self.assertEqual(summary, "uv run python -m unittest discover ...")

    def test_audit_state_redacts_token_like_values(self) -> None:
        self.write_audit_lines(
            {
                "ts": "2026-01-01T00:00:00+00:00",
                "event": "command",
                "title": "secret-token-value",
                "command": ["curl", "https://example.invalid/mcp?access_token=secret-token-value"],
            }
        )

        serialized = json.dumps(review.audit_state(), ensure_ascii=False)

        self.assertIn("[redacted]", serialized)
        self.assertNotIn("secret-token-value", serialized)
        self.assertNotIn("access_token", serialized)

    def test_env_status_hides_values(self) -> None:
        original = os.environ.get("MCP_ACCESS_TOKEN")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            self.assertEqual(review.env_status("MCP_ACCESS_TOKEN"), "set")

            del os.environ["MCP_ACCESS_TOKEN"]
            self.assertEqual(review.env_status("MCP_ACCESS_TOKEN"), "missing")
        finally:
            if original is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original

    def test_public_mcp_endpoint_hint_omits_token(self) -> None:
        original_host = os.environ.get("NGROK_HOST")
        original_base_url = os.environ.get("NGROK_BASE_URL")
        try:
            os.environ["NGROK_HOST"] = "example.ngrok-free.app?access_token=secret"
            os.environ["NGROK_BASE_URL"] = "https://ignored.example/mcp?access_token=secret"

            self.assertEqual(review.public_mcp_endpoint_hint(), "https://example.ngrok-free.app/mcp")
            self.assertNotIn("access_token", review.public_mcp_endpoint_hint() or "")
            self.assertNotIn("secret", review.public_mcp_endpoint_hint() or "")
        finally:
            if original_host is None:
                os.environ.pop("NGROK_HOST", None)
            else:
                os.environ["NGROK_HOST"] = original_host

            if original_base_url is None:
                os.environ.pop("NGROK_BASE_URL", None)
            else:
                os.environ["NGROK_BASE_URL"] = original_base_url

    def test_normalize_server_tab(self) -> None:
        self.assertEqual(review.normalize_server_tab(None), "overview")
        self.assertEqual(review.normalize_server_tab("services"), "services")
        self.assertEqual(review.normalize_server_tab("processes"), "processes")
        self.assertEqual(review.normalize_server_tab("bad-value"), "overview")

    def test_tcp_port_reachable_false_for_invalid_or_unused_port(self) -> None:
        self.assertFalse(review.tcp_port_reachable("127.0.0.1", 0))

        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", 0))
            unused_port = int(sock.getsockname()[1])
        finally:
            sock.close()

        self.assertFalse(review.tcp_port_reachable("127.0.0.1", unused_port, timeout_seconds=0.05))

    def test_server_state_does_not_include_token_value(self) -> None:
        original_token = os.environ.get("MCP_ACCESS_TOKEN")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            serialized = json.dumps(review.server_state(), ensure_ascii=False)

            self.assertIn('"mcp_access_token": "set"', serialized)
            self.assertNotIn("secret-token-value", serialized)
            self.assertNotIn("access_token=", serialized)
        finally:
            if original_token is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original_token

    def test_server_tab_content_omits_token_value(self) -> None:
        original_token = os.environ.get("MCP_ACCESS_TOKEN")
        original_host = os.environ.get("NGROK_HOST")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            os.environ["NGROK_HOST"] = "example.ngrok-free.app?access_token=secret-token-value"
            html = review.server_tab_content_html("connection", review.server_state())

            self.assertIn("https://&lt;NGROK_HOST&gt;/mcp?access_token=&lt;TOKEN&gt;", html)
            self.assertNotIn("secret-token-value", html)
            self.assertNotIn("example.ngrok-free.app?access_token", html)
        finally:
            if original_token is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original_token

            if original_host is None:
                os.environ.pop("NGROK_HOST", None)
            else:
                os.environ["NGROK_HOST"] = original_host

    def test_diagnostics_tab_shows_embedded_watcher_settings(self) -> None:
        html = review.server_tab_content_html("diagnostics", review.server_state())

        self.assertIn("Embedded watcher", html)
        self.assertIn("Watcher open mode", html)
        self.assertIn("Notification target", html)
        self.assertIn("Notification click action", html)
        self.assertIn("최근 로컬 작업 이벤트", html)
        self.assertIn("/api/audit-state", html)

    def test_primary_nav_html_uses_large_category_labels(self) -> None:
        html = review.primary_nav_html("history")

        self.assertIn("승인", html)
        self.assertIn("이력/결과", html)
        self.assertIn("관리", html)
        self.assertIn('aria-current="page"', html)

    def test_management_nav_html_contains_internal_tab_labels(self) -> None:
        html = review.management_nav_html("overview")

        for label in ("개요", "서버", "프로세스", "연결", "환경", "로컬 도구", "진단"):
            self.assertIn(label, html)

    def test_supervisor_state_reports_missing_services(self) -> None:
        root = Path(self.tmp.name) / "runtime"
        review.RUNTIME_ROOT = root

        state = review.supervisor_state()
        services = {item["name"]: item for item in state["services"]}

        self.assertEqual(state["runtime_root"], str(root))
        self.assertEqual(state["process_dir"], str(root / "processes"))
        self.assertEqual(services["review"]["pid"], None)
        self.assertEqual(services["review"]["state"], "no")
        self.assertEqual(services["review"]["managed"], False)
        self.assertEqual(services["ngrok"]["reachable"], None)

    def test_supervisor_state_reports_stale_pid_file_without_cleanup(self) -> None:
        root = Path(self.tmp.name) / "runtime"
        review.RUNTIME_ROOT = root
        process_dir = root / "processes"
        process_dir.mkdir(parents=True)
        pid_file = process_dir / "mcp.pid"
        pid_file.write_text("99999999\n", encoding="utf-8")

        services = {item["name"]: item for item in review.supervisor_state()["services"]}

        self.assertEqual(services["mcp"]["pid"], 99999999)
        self.assertEqual(services["mcp"]["state"], "stale")
        self.assertEqual(services["mcp"]["managed"], False)
        self.assertEqual(services["mcp"]["managed_state"], "stale")
        self.assertTrue(pid_file.exists())

    def test_supervisor_state_omits_token_values(self) -> None:
        original_token = os.environ.get("MCP_ACCESS_TOKEN")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            serialized = json.dumps(review.supervisor_state(), ensure_ascii=False)

            self.assertNotIn("secret-token-value", serialized)
            self.assertNotIn("access_token", serialized)
        finally:
            if original_token is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original_token

    def test_processes_tab_renders_supervisor_status(self) -> None:
        root = Path(self.tmp.name) / "runtime"
        review.RUNTIME_ROOT = root
        html = review.server_tab_content_html("processes", review.server_state())

        self.assertIn("Supervisor processes", html)
        self.assertIn("scripts/dev_session.sh start", html)
        self.assertIn("scripts/dev_session.sh status", html)
        self.assertIn("scripts/dev_session.sh restart [mcp|ngrok]", html)
        self.assertIn('/servers/processes/start/mcp', html)
        self.assertIn('/servers/processes/start/ngrok', html)
        self.assertNotIn('/servers/processes/restart/review', html)
        self.assertNotIn('/servers/processes/start/review', html)
        self.assertNotIn('/servers/processes/stop/review', html)
        self.assertIn("scripts/dev_session.sh logs [review|mcp|ngrok]", html)
        self.assertIn("scripts/dev_session.sh stop", html)
        self.assertIn(str(root / "processes"), html)
        self.assertIn("/api/supervisor-state", html)
        self.assertIn("data-table process-table", html)
        self.assertIn(">review.log</code>", html)
        self.assertIn(">review.pid</code>", html)
        self.assertIn(f'title="{root / "processes" / "review.log"}"', html)
        self.assertIn("/servers/session/stop/confirm", html)
        self.assertIn("/servers/session/restart/confirm", html)

    def test_full_session_stop_and_restart_pages_render(self) -> None:
        stop_confirm_html = review.full_session_stop_confirm_html()
        stopping_html = review.full_session_stopping_html()
        restart_confirm_html = review.full_session_restart_confirm_html()
        restarting_html = review.full_session_restarting_html()

        self.assertIn("/servers/session/stop", stop_confirm_html)
        self.assertIn("Stop full session", stop_confirm_html)
        self.assertIn("scripts/dev_session.sh start", stopping_html)
        self.assertIn("Full session stop requested", stopping_html)
        self.assertIn("/servers/session/restart", restart_confirm_html)
        self.assertIn("Restart full session", restart_confirm_html)
        self.assertIn("scripts/dev_session.sh restart-session", restart_confirm_html)
        self.assertIn("Full session restart requested", restarting_html)

    def test_schedule_full_session_restart_uses_detached_popen(self) -> None:
        source = inspect.getsource(review.schedule_full_session_restart)

        self.assertIn("subprocess.Popen", source)
        self.assertIn("start_new_session=True", source)
        self.assertNotIn("subprocess.run", source)

    def test_processes_tab_renders_running_service_controls(self) -> None:
        html = review.supervisor_processes_html(
            {
                "services": [
                    {
                        "name": "mcp",
                        "pid": 12345,
                        "state": "yes",
                        "managed_state": "yes",
                        "reachable": True,
                        "host": "127.0.0.1",
                        "port": 8787,
                        "log_file": "/tmp/mcp.log",
                        "pid_file": "/tmp/mcp.pid",
                    }
                ]
            }
        )

        self.assertIn('/servers/processes/stop/mcp', html)
        self.assertIn('/servers/processes/restart/mcp', html)
        self.assertNotIn('/servers/processes/start/mcp', html)

    def test_processes_tab_renders_action_success_notice(self) -> None:
        root = Path(self.tmp.name) / "runtime"
        review.RUNTIME_ROOT = root
        notice = review.supervisor_action_notice_html("start", "mcp", "ok")
        html = review.server_tab_content_html("processes", review.server_state(), action_notice_html=notice)

        self.assertIn("Start completed", html)
        self.assertIn("mcp", html)
        self.assertEqual(review.supervisor_action_notice_html("start", "review", "ok"), "")
        self.assertEqual(review.supervisor_action_notice_html("start", "mcp", "failed"), "")
        self.assertEqual(review.supervisor_action_notice_html("delete", "mcp", "ok"), "")

    def test_environment_tab_omits_token_and_renders_long_label(self) -> None:
        original_token = os.environ.get("MCP_ACCESS_TOKEN")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            html = review.server_tab_content_html("environment", review.server_state())

            self.assertIn("NGROK_HOST/NGROK_BASE_URL", html)
            self.assertIn("MCP_ACCESS_TOKEN", html)
            self.assertIn("set", html)
            self.assertNotIn("secret-token-value", html)
        finally:
            if original_token is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original_token

    def test_mask_sensitive_text_redacts_tokens(self) -> None:
        original_token = os.environ.get("MCP_ACCESS_TOKEN")
        try:
            os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"
            text = (
                "MCP_ACCESS_TOKEN=secret-token-value "
                "https://example.invalid/mcp?access_token=query-secret "
                "Authorization: Bearer bearer-secret "
                "Bearer loose-secret"
            )
            masked = review.mask_sensitive_text(text)

            self.assertNotIn("secret-token-value", masked)
            self.assertNotIn("query-secret", masked)
            self.assertNotIn("bearer-secret", masked)
            self.assertNotIn("loose-secret", masked)
            self.assertIn("access_token=[redacted]", masked)
            self.assertIn("Bearer [redacted]", masked)
        finally:
            if original_token is None:
                os.environ.pop("MCP_ACCESS_TOKEN", None)
            else:
                os.environ["MCP_ACCESS_TOKEN"] = original_token

    def test_mask_sensitive_text_redacts_ngrok_authtoken(self) -> None:
        original_token = os.environ.get("NGROK_AUTHTOKEN")
        try:
            os.environ["NGROK_AUTHTOKEN"] = "ngrok-secret-value"
            text = "NGROK_AUTHTOKEN=ngrok-secret-value raw=ngrok-secret-value"
            masked = review.mask_sensitive_text(text)

            self.assertNotIn("ngrok-secret-value", masked)
            self.assertIn("NGROK_AUTHTOKEN=[redacted]", masked)
        finally:
            if original_token is None:
                os.environ.pop("NGROK_AUTHTOKEN", None)
            else:
                os.environ["NGROK_AUTHTOKEN"] = original_token

    def test_supervisor_control_html_renders_start_for_stopped_or_stale_services(self) -> None:
        stopped_html = review.supervisor_control_html("mcp", "no")
        stale_html = review.supervisor_control_html("ngrok", "stale")

        self.assertIn('/servers/processes/start/mcp', stopped_html)
        self.assertNotIn('/servers/processes/stop/mcp', stopped_html)
        self.assertNotIn('/servers/processes/restart/mcp', stopped_html)
        self.assertIn('/servers/processes/start/ngrok', stale_html)
        self.assertNotIn('/servers/processes/stop/ngrok', stale_html)
        self.assertNotIn('/servers/processes/restart/ngrok', stale_html)

    def test_supervisor_control_html_keeps_review_terminal_only(self) -> None:
        html = review.supervisor_control_html("review", "yes")

        self.assertIn("terminal only", html)
        self.assertNotIn("<form", html)
        self.assertNotIn('/servers/processes/stop/review', html)
        self.assertNotIn('/servers/processes/restart/review', html)

    def test_status_badge_includes_text_label(self) -> None:
        html = review.status_badge("reachable", "ok")

        self.assertIn("reachable", html)
        self.assertIn("badge ok", html)

    def test_app_shell_includes_sidebar_brand_and_management_nav(self) -> None:
        html = review.app_shell(
            "관리",
            "<p>body</p>",
            active_nav="servers",
            server_tab="environment",
        ).decode("utf-8")

        self.assertIn("Workspace Terminal Bridge", html)
        self.assertIn("Local MCP review panel", html)
        self.assertIn("환경", html)
        self.assertIn('aria-current="page"', html)

    def test_app_shell_css_prevents_pending_page_horizontal_overflow(self) -> None:
        html = review.app_shell(
            "승인",
            review.approval_mode_card_html("yolo") + review.latest_handoff_html() + review.intent_inbox_html(),
            active_nav="pending",
        ).decode("utf-8")

        self.assertIn("overflow-x: hidden", html)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(260px, 1fr))", html)
        self.assertIn("white-space: pre-wrap", html)
        self.assertIn("overflow-wrap: anywhere", html)
        self.assertIn("max-width: 100%", html)


class WatcherHelperTests(unittest.TestCase):
    def test_embedded_watcher_config_defaults(self) -> None:
        names = (
            "BUNDLE_REVIEW_EMBEDDED_WATCHER",
            "BUNDLE_WATCH_OPEN_MODE",
            "BUNDLE_WATCH_NOTIFY",
            "BUNDLE_WATCH_NOTIFICATION_TARGET",
            "BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION",
        )
        original = {name: os.environ.get(name) for name in names}
        try:
            for name in names:
                os.environ.pop(name, None)

            config = review.embedded_watcher_config()

            self.assertTrue(config["enabled"])
            self.assertEqual(config["open_mode"], "dashboard_once")
            self.assertTrue(config["notify_enabled"])
            self.assertEqual(config["notification_target"], "pending")
            self.assertEqual(config["notification_click_action"], "focus")
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_parse_bool_env_for_embedded_watcher_flag(self) -> None:
        self.assertTrue(notifications.parse_bool_env(None, default=True))
        self.assertTrue(notifications.parse_bool_env("1", default=False))
        self.assertTrue(notifications.parse_bool_env("true", default=False))
        self.assertTrue(notifications.parse_bool_env("yes", default=False))
        self.assertTrue(notifications.parse_bool_env("on", default=False))
        self.assertFalse(notifications.parse_bool_env("", default=True))
        self.assertFalse(notifications.parse_bool_env("0", default=True))
        self.assertFalse(notifications.parse_bool_env("false", default=True))
        self.assertFalse(notifications.parse_bool_env("no", default=True))
        self.assertFalse(notifications.parse_bool_env("off", default=True))

    def test_parse_open_mode(self) -> None:
        self.assertEqual(watcher.parse_open_mode(None), "dashboard_once")
        self.assertEqual(watcher.parse_open_mode("bundle"), "bundle")
        self.assertEqual(watcher.parse_open_mode("none"), "none")
        self.assertEqual(watcher.parse_open_mode("bad-value"), "dashboard_once")

    def test_parse_notify_flag(self) -> None:
        self.assertTrue(watcher.parse_notify_flag(None))
        self.assertTrue(watcher.parse_notify_flag("1"))
        self.assertTrue(watcher.parse_notify_flag("true"))
        self.assertTrue(watcher.parse_notify_flag("yes"))
        self.assertTrue(watcher.parse_notify_flag("on"))
        self.assertFalse(watcher.parse_notify_flag(""))
        self.assertFalse(watcher.parse_notify_flag("0"))
        self.assertFalse(watcher.parse_notify_flag("false"))
        self.assertFalse(watcher.parse_notify_flag("no"))
        self.assertFalse(watcher.parse_notify_flag("off"))

    def test_parse_notification_target(self) -> None:
        self.assertEqual(watcher.parse_notification_target(None), "pending")
        self.assertEqual(watcher.parse_notification_target("bundle"), "bundle")
        self.assertEqual(watcher.parse_notification_target("pending"), "pending")
        self.assertEqual(watcher.parse_notification_target("bad-value"), "pending")

    def test_parse_notification_click_action(self) -> None:
        self.assertEqual(watcher.parse_notification_click_action(None), "focus")
        self.assertEqual(watcher.parse_notification_click_action("focus"), "focus")
        self.assertEqual(watcher.parse_notification_click_action("open"), "open")
        self.assertEqual(watcher.parse_notification_click_action("bad-value"), "focus")

    def test_notification_url(self) -> None:
        base_url = "http://127.0.0.1:8790"

        self.assertEqual(
            watcher.notification_url("cmd-test", "bundle", base_url),
            "http://127.0.0.1:8790/bundles/cmd-test",
        )
        self.assertEqual(
            watcher.notification_url("cmd-test", "pending", base_url),
            "http://127.0.0.1:8790/pending",
        )
        self.assertEqual(
            notifications.notification_url(
                "http://127.0.0.1:8790?access_token=secret-token-value",
                "cmd-test",
                "pending",
            ),
            "http://127.0.0.1:8790/pending",
        )

    def test_terminal_notifier_command_focus_action(self) -> None:
        command = watcher.terminal_notifier_command(
            "cmd-test",
            "bundle",
            "http://127.0.0.1:8790",
        )

        self.assertEqual(command[0], "terminal-notifier")
        self.assertIn("-execute", command)
        execute_value = command[command.index("-execute") + 1]
        self.assertIn("scripts/focus_review_url.py", execute_value)
        self.assertIn("http://127.0.0.1:8790/bundles/cmd-test", execute_value)
        self.assertIn("http://127.0.0.1:8790", execute_value)
        self.assertIn("-group", command)
        self.assertIn("workspace-terminal-bridge", command)

    def test_terminal_notifier_command_open_action(self) -> None:
        command = watcher.terminal_notifier_command(
            "cmd-test",
            "bundle",
            "http://127.0.0.1:8790",
            "open",
        )

        self.assertIn("-open", command)
        self.assertIn("http://127.0.0.1:8790/bundles/cmd-test", command)
        self.assertNotIn("-execute", command)

    def test_terminal_notifier_command_omits_token_from_url(self) -> None:
        command = notifications.build_terminal_notifier_command(
            "http://127.0.0.1:8790?access_token=secret-token-value",
            "cmd-test",
            "pending",
        )
        serialized = " ".join(command)

        self.assertIn("http://127.0.0.1:8790/pending", serialized)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("secret-token-value", serialized)


if __name__ == "__main__":
    unittest.main()
