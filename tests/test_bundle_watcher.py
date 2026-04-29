from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from scripts import command_bundle_review_server as review
from scripts import command_bundle_watcher as standalone_watcher
from terminal_bridge import bundle_watcher


def low_risk_command_bundle() -> dict[str, object]:
    return {
        "bundle_id": "cmd-test",
        "status": "pending",
        "risk": "low",
        "steps": [{"type": "command", "risk": "low", "argv": ["git", "status"]}],
    }


class BundleWatcherHelperTests(unittest.TestCase):
    def test_load_bundle_record_returns_dict_or_none_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid_path = root / "cmd-valid.json"
            broken_path = root / "cmd-broken.json"
            list_path = root / "cmd-list.json"

            valid_path.write_text(json.dumps({"bundle_id": "cmd-valid"}), encoding="utf-8")
            broken_path.write_text("{not-json", encoding="utf-8")
            list_path.write_text(json.dumps(["not", "dict"]), encoding="utf-8")

            self.assertEqual(bundle_watcher.load_bundle_record(valid_path), {"bundle_id": "cmd-valid"})
            self.assertIsNone(bundle_watcher.load_bundle_record(broken_path))
            self.assertIsNone(bundle_watcher.load_bundle_record(list_path))

    def test_current_pending_bundle_ids_reads_cmd_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pending_dir = Path(tmp)
            (pending_dir / "cmd-one.json").write_text(json.dumps({"bundle_id": "cmd-custom"}), encoding="utf-8")
            (pending_dir / "cmd-two.json").write_text("{broken-json", encoding="utf-8")
            (pending_dir / "note.json").write_text(json.dumps({"bundle_id": "cmd-ignored"}), encoding="utf-8")

            self.assertEqual(bundle_watcher.current_pending_bundle_ids(pending_dir), {"cmd-custom", "cmd-two"})

    def test_handle_pending_bundle_auto_applies_when_mode_allows(self) -> None:
        calls: list[tuple[str, str]] = []
        notifications: list[str] = []

        def fake_auto_apply(bundle_id: str, _runner: Path, _project_root: Path, source: str, _prefix: str) -> bool:
            calls.append((bundle_id, source))
            return True

        with contextlib.redirect_stdout(io.StringIO()):
            result = bundle_watcher.handle_pending_bundle(
                "cmd-test",
                low_risk_command_bundle(),
                approval_mode="safe-auto",
                runner=Path("runner.py"),
                project_root=Path("."),
                notify_enabled=True,
                notify_bundle=notifications.append,
                open_mode="bundle",
                open_bundle=notifications.append,
                auto_apply_func=fake_auto_apply,
            )

        self.assertEqual(result, "auto-applied")
        self.assertEqual(calls, [("cmd-test", "mode=safe-auto")])
        self.assertEqual(notifications, [])

    def test_handle_pending_bundle_normal_mode_does_not_auto_apply(self) -> None:
        calls: list[str] = []
        notifications: list[str] = []
        opened: list[str] = []

        def fake_auto_apply(bundle_id: str, _runner: Path, _project_root: Path, _source: str, _prefix: str) -> bool:
            calls.append(bundle_id)
            return True

        result = bundle_watcher.handle_pending_bundle(
            "cmd-test",
            low_risk_command_bundle(),
            approval_mode="normal",
            runner=Path("runner.py"),
            project_root=Path("."),
            notify_enabled=True,
            notify_bundle=notifications.append,
            open_mode="bundle",
            open_bundle=opened.append,
            auto_apply_func=fake_auto_apply,
        )

        self.assertEqual(result, "manual")
        self.assertEqual(calls, [])
        self.assertEqual(notifications, ["cmd-test"])
        self.assertEqual(opened, ["cmd-test"])

    def test_handle_pending_bundle_uses_shared_approval_decision(self) -> None:
        original = bundle_watcher.should_auto_approve
        calls: list[tuple[dict[str, object], str]] = []
        auto_applied: list[str] = []

        def fake_should_auto_approve(record: dict[str, object], mode: str) -> bool:
            calls.append((record, mode))
            return mode == "yolo"

        def fake_auto_apply(bundle_id: str, _runner: Path, _project_root: Path, _source: str, _prefix: str) -> bool:
            auto_applied.append(bundle_id)
            return True

        try:
            bundle_watcher.should_auto_approve = fake_should_auto_approve
            record = {"bundle_id": "cmd-test", "status": "pending", "risk": "high"}

            with contextlib.redirect_stdout(io.StringIO()):
                result = bundle_watcher.handle_pending_bundle(
                    "cmd-test",
                    record,
                    approval_mode="yolo",
                    runner=Path("runner.py"),
                    project_root=Path("."),
                    notify_enabled=False,
                    notify_bundle=None,
                    open_mode="dashboard_once",
                    open_bundle=None,
                    auto_apply_func=fake_auto_apply,
                )
        finally:
            bundle_watcher.should_auto_approve = original

        self.assertEqual(result, "auto-applied")
        self.assertEqual(calls, [(record, "yolo")])
        self.assertEqual(auto_applied, ["cmd-test"])

    def test_watch_pending_bundles_processes_once_and_marks_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pending_dir = Path(tmp)
            (pending_dir / "cmd-test.json").write_text(json.dumps(low_risk_command_bundle()), encoding="utf-8")
            seen: set[str] = set()
            notifications: list[str] = []

            class OneWaitStop:
                def is_set(self) -> bool:
                    return False

                def wait(self, _timeout: float) -> bool:
                    return True

            with contextlib.redirect_stdout(io.StringIO()):
                bundle_watcher.watch_pending_bundles(
                    pending_dir=pending_dir,
                    runner=Path("runner.py"),
                    project_root=Path("."),
                    seen_bundle_ids=seen,
                    poll_seconds=0.01,
                    notify_enabled=True,
                    notify_bundle=notifications.append,
                    open_mode="dashboard_once",
                    open_bundle=None,
                    stop_event=OneWaitStop(),
                    load_mode=lambda: "normal",
                )

            self.assertEqual(seen, {"cmd-test"})
            self.assertEqual(notifications, ["cmd-test"])

    def test_standalone_watcher_imports_shared_module(self) -> None:
        self.assertIs(standalone_watcher.bundle_watcher, bundle_watcher)

    def test_embedded_watcher_loop_uses_shared_module(self) -> None:
        original = bundle_watcher.watch_pending_bundles
        calls: list[dict[str, object]] = []

        def fake_watch_pending_bundles(**kwargs: object) -> None:
            calls.append(kwargs)

        try:
            bundle_watcher.watch_pending_bundles = fake_watch_pending_bundles
            review.embedded_watcher_loop(
                threading.Event(),
                {"cmd-existing"},
                {
                    "base_url": "http://127.0.0.1:8790",
                    "open_mode": "dashboard_once",
                    "notify_enabled": False,
                    "notification_target": "pending",
                    "notification_click_action": "focus",
                    "poll_seconds": 0.01,
                    "osascript_fallback": False,
                },
            )
        finally:
            bundle_watcher.watch_pending_bundles = original

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["pending_dir"], review.PENDING_DIR)
        self.assertEqual(calls[0]["seen_bundle_ids"], {"cmd-existing"})
        self.assertEqual(calls[0]["log_prefix"], "[review-ui] ")


if __name__ == "__main__":
    unittest.main()
