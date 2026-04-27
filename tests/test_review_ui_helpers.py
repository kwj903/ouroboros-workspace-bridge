from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

from scripts import command_bundle_review_server as review
from scripts import command_bundle_watcher as watcher
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

        review.PENDING_DIR = root / "pending"
        review.APPLIED_DIR = root / "applied"
        review.REJECTED_DIR = root / "rejected"
        review.FAILED_DIR = root / "failed"

        for directory in review.bundle_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        (
            review.PENDING_DIR,
            review.APPLIED_DIR,
            review.REJECTED_DIR,
            review.FAILED_DIR,
        ) = self.original_dirs
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

    def test_primary_nav_html_uses_large_category_labels(self) -> None:
        html = review.primary_nav_html("history")

        self.assertIn("승인", html)
        self.assertIn("이력/결과", html)
        self.assertIn("관리", html)
        self.assertIn('aria-current="page"', html)

    def test_management_nav_html_contains_internal_tab_labels(self) -> None:
        html = review.management_nav_html("overview")

        for label in ("개요", "서버", "연결", "환경", "로컬 도구", "진단"):
            self.assertIn(label, html)

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
