from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from terminal_bridge import session_supervisor as supervisor
from terminal_bridge.version import version_summary


@dataclass(frozen=True)
class LocalizedText:
    en: str
    ko: str

    def get(self, language: str) -> str:
        return self.ko if language == "ko" else self.en


@dataclass(frozen=True)
class CommandHelp:
    name: str
    category: LocalizedText
    usage: str
    summary: LocalizedText
    details: LocalizedText
    examples: tuple[str, ...] = ()
    caution: LocalizedText | None = None
    aliases: tuple[str, ...] = ()


CATEGORY_SETUP = LocalizedText("Setup", "설정")
CATEGORY_SESSION = LocalizedText("Session", "세션")
CATEGORY_CONNECTION = LocalizedText("Connection", "연결")
CATEGORY_DEBUG = LocalizedText("Service debug", "서비스 디버그")
CATEGORY_STORAGE = LocalizedText("Runtime storage", "런타임 저장소")
CATEGORY_META = LocalizedText("Meta", "기타")


COMMAND_HELP: tuple[CommandHelp, ...] = (
    CommandHelp(
        name="setup",
        aliases=("configure",),
        category=CATEGORY_SETUP,
        usage="uv run woojae setup",
        summary=LocalizedText(
            "Configure local bridge settings.",
            "로컬 브리지 설정을 구성합니다.",
        ),
        details=LocalizedText(
            "Runs the setup flow for WORKSPACE_ROOT, ngrok host, access token, and local runtime settings. "
            "The configure command is kept as an alias for compatibility.",
            "WORKSPACE_ROOT, ngrok host, access token, 로컬 런타임 설정을 구성하는 설정 흐름을 실행합니다. "
            "configure 명령은 호환성을 위한 별칭입니다.",
        ),
        examples=("uv run woojae setup", "uv run woojae configure"),
        caution=LocalizedText(
            "Do not paste real tokens, ngrok authtokens, .env values, or private file contents into public issues.",
            "실제 토큰, ngrok authtoken, .env 값, 비공개 파일 내용은 공개 이슈에 붙여넣지 마세요.",
        ),
    ),
    CommandHelp(
        name="checklist",
        category=CATEGORY_SETUP,
        usage="uv run woojae checklist",
        summary=LocalizedText(
            "Print the local setup checklist.",
            "로컬 설정 체크리스트를 출력합니다.",
        ),
        details=LocalizedText(
            "Shows the recommended steps for preparing and connecting the local bridge.",
            "로컬 브리지를 준비하고 연결하기 위한 권장 절차를 보여줍니다.",
        ),
        examples=("uv run woojae checklist",),
    ),
    CommandHelp(
        name="doctor",
        category=CATEGORY_SETUP,
        usage="uv run woojae doctor",
        summary=LocalizedText(
            "Check local runtime configuration and dependencies.",
            "로컬 런타임 설정과 의존성을 점검합니다.",
        ),
        details=LocalizedText(
            "Runs local checks that help diagnose missing settings, tools, or session prerequisites.",
            "누락된 설정, 도구, 세션 준비 상태를 진단하기 위한 로컬 점검을 실행합니다.",
        ),
        examples=("uv run woojae doctor",),
    ),
    CommandHelp(
        name="start",
        category=CATEGORY_SESSION,
        usage="uv run woojae start",
        summary=LocalizedText(
            "Start the local review, MCP, and ngrok session.",
            "로컬 review, MCP, ngrok 세션을 시작합니다.",
        ),
        details=LocalizedText(
            "Starts the local processes required for ChatGPT to connect through the Workspace Bridge.",
            "ChatGPT가 Workspace Bridge를 통해 연결하는 데 필요한 로컬 프로세스들을 시작합니다.",
        ),
        examples=("uv run woojae start", "uv run woojae status"),
    ),
    CommandHelp(
        name="status",
        category=CATEGORY_SESSION,
        usage="uv run woojae status",
        summary=LocalizedText(
            "Show local session status.",
            "로컬 세션 상태를 표시합니다.",
        ),
        details=LocalizedText(
            "Checks whether the review UI, MCP server, and ngrok tunnel appear to be running and reachable.",
            "review UI, MCP 서버, ngrok 터널이 실행 중이고 접근 가능한지 확인합니다.",
        ),
        examples=("uv run woojae status",),
    ),
    CommandHelp(
        name="open",
        category=CATEGORY_SESSION,
        usage="uv run woojae open",
        summary=LocalizedText(
            "Open the local review dashboard.",
            "로컬 review 대시보드를 엽니다.",
        ),
        details=LocalizedText(
            "Opens the browser page used to review, approve, or reject pending bundles.",
            "pending bundle을 검토, 승인, 거절하는 브라우저 페이지를 엽니다.",
        ),
        examples=("uv run woojae open",),
    ),
    CommandHelp(
        name="review",
        category=CATEGORY_SESSION,
        usage="uv run woojae review",
        summary=LocalizedText(
            "Run the review UI in the foreground.",
            "review UI를 포그라운드에서 실행합니다.",
        ),
        details=LocalizedText(
            "Useful for debugging the local review server directly instead of running a full managed session.",
            "전체 관리 세션 대신 로컬 review 서버를 직접 디버깅할 때 유용합니다.",
        ),
        examples=("uv run woojae review",),
    ),
    CommandHelp(
        name="stop",
        category=CATEGORY_SESSION,
        usage="uv run woojae stop",
        summary=LocalizedText(
            "Stop the local session.",
            "로컬 세션을 중지합니다.",
        ),
        details=LocalizedText(
            "Stops the managed local processes for the current bridge session.",
            "현재 브리지 세션의 관리 대상 로컬 프로세스들을 중지합니다.",
        ),
        examples=("uv run woojae stop",),
    ),
    CommandHelp(
        name="restart-session",
        category=CATEGORY_SESSION,
        usage="uv run woojae restart-session",
        summary=LocalizedText(
            "Restart the full local session.",
            "전체 로컬 세션을 재시작합니다.",
        ),
        details=LocalizedText(
            "Restarts the review UI, MCP server, and ngrok tunnel together. Use this after code or configuration changes.",
            "review UI, MCP 서버, ngrok 터널을 함께 재시작합니다. 코드나 설정 변경 후 사용하세요.",
        ),
        examples=("uv run woojae restart-session", "uv run woojae status"),
    ),
    CommandHelp(
        name="mcp-url",
        category=CATEGORY_CONNECTION,
        usage="uv run woojae mcp-url",
        summary=LocalizedText(
            "Print a redacted MCP URL preview.",
            "마스킹된 MCP URL 미리보기를 출력합니다.",
        ),
        details=LocalizedText(
            "Shows whether a configured MCP URL can be derived without printing the real access token.",
            "실제 access token을 출력하지 않고 설정된 MCP URL을 만들 수 있는지 보여줍니다.",
        ),
        examples=("uv run woojae mcp-url",),
        caution=LocalizedText(
            "Use copy-url when you need the real URL for ChatGPT connector setup.",
            "ChatGPT 커넥터 설정에 실제 URL이 필요하면 copy-url을 사용하세요.",
        ),
    ),
    CommandHelp(
        name="copy-url",
        category=CATEGORY_CONNECTION,
        usage="uv run woojae copy-url",
        summary=LocalizedText(
            "Copy the real MCP URL to the clipboard.",
            "실제 MCP URL을 클립보드에 복사합니다.",
        ),
        details=LocalizedText(
            "Copies the MCP server URL, including the access token, using the OS clipboard utility when available.",
            "OS 클립보드 도구를 사용해 access token이 포함된 MCP 서버 URL을 복사합니다.",
        ),
        examples=("uv run woojae copy-url",),
        caution=LocalizedText(
            "The copied URL contains a secret access token. Do not paste it into public issues, chats, or logs.",
            "복사된 URL에는 비밀 access token이 포함됩니다. 공개 이슈, 채팅, 로그에 붙여넣지 마세요.",
        ),
    ),
    CommandHelp(
        name="logs",
        category=CATEGORY_DEBUG,
        usage="uv run woojae logs [review|mcp|ngrok]",
        summary=LocalizedText(
            "Print logs for one service or all services.",
            "특정 서비스 또는 전체 서비스 로그를 출력합니다.",
        ),
        details=LocalizedText(
            "Use this when status shows a service is not alive or not reachable.",
            "status에서 서비스가 살아 있지 않거나 접근 불가로 보일 때 사용합니다.",
        ),
        examples=("uv run woojae logs", "uv run woojae logs mcp", "uv run woojae logs ngrok"),
    ),
    CommandHelp(
        name="restart",
        category=CATEGORY_DEBUG,
        usage="uv run woojae restart [mcp|ngrok]",
        summary=LocalizedText(
            "Restart one managed service.",
            "관리 대상 서비스 하나를 재시작합니다.",
        ),
        details=LocalizedText(
            "Restarts only the selected service. For broad recovery, prefer restart-session.",
            "선택한 서비스만 재시작합니다. 전반적인 복구가 목적이면 restart-session을 우선 사용하세요.",
        ),
        examples=("uv run woojae restart mcp", "uv run woojae restart ngrok"),
    ),
    CommandHelp(
        name="start-service",
        category=CATEGORY_DEBUG,
        usage="uv run woojae start-service [mcp|ngrok]",
        summary=LocalizedText(
            "Start one managed service.",
            "관리 대상 서비스 하나를 시작합니다.",
        ),
        details=LocalizedText(
            "Low-level fallback command for starting only the MCP server or ngrok process.",
            "MCP 서버 또는 ngrok 프로세스만 시작하는 저수준 fallback 명령입니다.",
        ),
        examples=("uv run woojae start-service mcp", "uv run woojae start-service ngrok"),
    ),
    CommandHelp(
        name="stop-service",
        category=CATEGORY_DEBUG,
        usage="uv run woojae stop-service [mcp|ngrok]",
        summary=LocalizedText(
            "Stop one managed service.",
            "관리 대상 서비스 하나를 중지합니다.",
        ),
        details=LocalizedText(
            "Low-level fallback command for stopping only the MCP server or ngrok process.",
            "MCP 서버 또는 ngrok 프로세스만 중지하는 저수준 fallback 명령입니다.",
        ),
        examples=("uv run woojae stop-service mcp", "uv run woojae stop-service ngrok"),
    ),
    CommandHelp(
        name="paths",
        category=CATEGORY_STORAGE,
        usage="uv run woojae paths",
        summary=LocalizedText(
            "Print project, runtime, and workspace paths.",
            "프로젝트, 런타임, 워크스페이스 경로를 출력합니다.",
        ),
        details=LocalizedText(
            "Shows where the repository, WORKSPACE_ROOT, runtime root, settings, logs, backups, and bundles are located.",
            "레포지토리, WORKSPACE_ROOT, runtime root, 설정, 로그, 백업, 번들 위치를 보여줍니다.",
        ),
        examples=("uv run woojae paths",),
    ),
    CommandHelp(
        name="storage",
        category=CATEGORY_STORAGE,
        usage="uv run woojae storage",
        summary=LocalizedText(
            "Print runtime storage usage by category.",
            "런타임 저장소 사용량을 범주별로 출력합니다.",
        ),
        details=LocalizedText(
            "Summarizes runtime storage usage so you can decide whether cleanup is needed.",
            "cleanup이 필요한지 판단할 수 있도록 런타임 저장소 사용량을 요약합니다.",
        ),
        examples=("uv run woojae storage",),
    ),
    CommandHelp(
        name="cleanup",
        category=CATEGORY_STORAGE,
        usage="uv run woojae cleanup [--dry-run|--apply] [--older-than-days N] [--include-backups]",
        summary=LocalizedText(
            "Inspect or delete conservative runtime cleanup candidates.",
            "보수적으로 선별된 런타임 정리 후보를 확인하거나 삭제합니다.",
        ),
        details=LocalizedText(
            "Defaults to dry-run behavior unless --apply is explicitly used. Protected files, pending bundles, pid files, "
            "symlink candidates, and paths outside the runtime root are not cleanup targets.",
            "--apply를 명시하지 않으면 기본적으로 dry-run처럼 동작합니다. 보호 파일, pending bundle, pid 파일, "
            "symlink 후보, runtime root 밖 경로는 정리 대상이 아닙니다.",
        ),
        examples=(
            "uv run woojae cleanup --dry-run",
            "uv run woojae cleanup --apply",
            "uv run woojae cleanup --dry-run --older-than-days 14",
            "uv run woojae cleanup --dry-run --include-backups",
        ),
        caution=LocalizedText(
            "Always run --dry-run first and review the candidates before using --apply.",
            "항상 --dry-run을 먼저 실행하고 후보를 확인한 뒤 --apply를 사용하세요.",
        ),
    ),
    CommandHelp(
        name="version",
        category=CATEGORY_META,
        usage="uv run woojae version",
        summary=LocalizedText(
            "Show version and git metadata.",
            "버전과 git 메타데이터를 표시합니다.",
        ),
        details=LocalizedText(
            "Prints the package version plus commit, branch, and dirty-state metadata when available.",
            "패키지 버전과 가능한 경우 commit, branch, dirty 상태 메타데이터를 출력합니다.",
        ),
        examples=("uv run woojae version",),
    ),
    CommandHelp(
        name="help",
        category=CATEGORY_META,
        usage="uv run woojae help [command] [--lang auto|en|ko]",
        summary=LocalizedText(
            "Show this project-specific command guide.",
            "이 프로젝트 전용 명령어 가이드를 표시합니다.",
        ),
        details=LocalizedText(
            "Use this for workflow-oriented help. Use uv run woojae --help for argparse-level CLI syntax.",
            "작업 흐름 중심 도움말이 필요할 때 사용합니다. argparse 수준의 CLI 문법은 uv run woojae --help를 사용하세요.",
        ),
        examples=("uv run woojae help", "uv run woojae help cleanup", "uv run woojae help --lang ko"),
    ),
)


def command_help_lookup() -> dict[str, CommandHelp]:
    lookup: dict[str, CommandHelp] = {}
    for item in COMMAND_HELP:
        lookup[item.name] = item
        for alias in item.aliases:
            lookup[alias] = item
    return lookup


def help_summary(command_name: str) -> str | None:
    item = command_help_lookup().get(command_name)
    return item.summary.en if item else None


def language_from_locale(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.lower().replace("-", "_")
    for part in normalized.split(":"):
        if part.startswith("ko"):
            return "ko"
        if part.startswith("en"):
            return "en"
    return None


def saved_help_language() -> str:
    try:
        return supervisor.load_settings().help_language
    except Exception:
        return "auto"


def explicit_help_language(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in {"en", "ko"} else None


def resolve_help_language(language: str = "auto", saved_language: str | None = None) -> str:
    if language in {"en", "ko"}:
        return language
    env_language = explicit_help_language(os.environ.get("WOOJAE_HELP_LANG"))
    if env_language:
        return env_language
    stored_language = explicit_help_language(saved_language if saved_language is not None else saved_help_language())
    if stored_language:
        return stored_language
    for env_name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        detected = language_from_locale(os.environ.get(env_name))
        if detected:
            return detected
    return "en"


def print_command_help(topic: str | None = None, *, language: str = "auto") -> int:
    lang = resolve_help_language(language)
    lookup = command_help_lookup()

    if topic:
        item = lookup.get(topic)
        if item is None:
            if lang == "ko":
                print(f"[error] 알 수 없는 help 주제: {topic}", file=sys.stderr)
                print(file=sys.stderr)
                print("사용 가능한 주제:", file=sys.stderr)
            else:
                print(f"[error] Unknown help topic: {topic}", file=sys.stderr)
                print(file=sys.stderr)
                print("Available topics:", file=sys.stderr)
            for command_name in sorted(lookup):
                print(f"  {command_name}", file=sys.stderr)
            return 2

        print(item.name)
        print("=" * len(item.name))
        print()
        print(f"Usage: {item.usage}")
        print()
        print(item.summary.get(lang))
        print()
        print(item.details.get(lang))

        if item.examples:
            print()
            print("Examples:" if lang != "ko" else "예시:")
            for example in item.examples:
                print(f"  {example}")

        if item.caution:
            print()
            print("Caution:" if lang != "ko" else "주의:")
            print(f"  {item.caution.get(lang)}")

        return 0

    if lang == "ko":
        print("Ouroboros Workspace Bridge 명령어")
        print("===================================")
        print()
        print("기본 작업 흐름:")
    else:
        print("Ouroboros Workspace Bridge commands")
        print("===================================")
        print()
        print("Common workflow:")
    for command in (
        "uv run woojae setup",
        "uv run woojae doctor",
        "uv run woojae start",
        "uv run woojae status",
        "uv run woojae open",
        "uv run woojae copy-url",
    ):
        print(f"  {command}")

    current_category: str | None = None
    for item in COMMAND_HELP:
        category_key = item.category.en
        if category_key != current_category:
            current_category = category_key
            print()
            print(item.category.get(lang))
        print(f"  {item.name:<16} {item.summary.get(lang)}")

    print()
    if lang == "ko":
        print("상세 설명은 `uv run woojae help <명령어> --lang ko`로 확인하세요.")
        print("argparse 기본 CLI 문법은 `uv run woojae --help`로 확인하세요.")
    else:
        print("Run `uv run woojae help <command>` for details.")
        print("Run `uv run woojae --help` for argparse-level CLI help.")
    return 0


def run_dev_session(*args: str) -> int:
    """Backward-compatible adapter for the old dev_session helper commands."""
    if not args:
        return supervisor.print_checklist()

    command = args[0]
    if command == "configure":
        return supervisor.configure()
    if command == "checklist":
        return supervisor.print_checklist()
    if command == "doctor":
        return supervisor.doctor()
    if command == "review":
        return supervisor.review_foreground()
    if command == "start":
        return supervisor.start_session()
    if command == "status":
        return supervisor.status_session()
    if command == "stop":
        return supervisor.stop_session()
    if command == "restart-session":
        return supervisor.restart_session()
    if command == "start-service" and len(args) > 1:
        return supervisor.start_single_service(args[1])
    if command == "stop-service" and len(args) > 1:
        return supervisor.stop_single_service(args[1])
    if command == "restart" and len(args) > 1:
        return supervisor.restart_service(args[1])
    if command == "logs":
        return supervisor.logs_service(args[1] if len(args) > 1 else None)

    print(f"Unknown dev session command: {' '.join(args)}", file=sys.stderr)
    return 2


def configured_ngrok_host() -> str:
    return supervisor.load_settings().ngrok_host


def mcp_url(token: str) -> str | None:
    host = configured_ngrok_host()
    if not host:
        return None
    return f"https://{host}/mcp?access_token={token}"


def open_review_dashboard() -> int:
    return supervisor.open_review_dashboard()


def print_mcp_url_preview() -> int:
    return supervisor.mcp_url_preview()


def copy_mcp_url() -> int:
    return supervisor.copy_mcp_url()


def print_version_info() -> int:
    summary = version_summary()
    print(f"{summary['name']} {summary['version']}")
    print(f"commit: {summary['commit']}")
    print(f"branch: {summary['branch']}")
    print(f"dirty: {summary['dirty']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="woojae",
        description="Manage a local Workspace Terminal Bridge session.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("setup", "configure", "checklist", "doctor", "review", "start", "status", "stop"):
        subparsers.add_parser(name, help=help_summary(name))

    subparsers.add_parser("restart-session", help=help_summary("restart-session"))

    for name in ("start-service", "stop-service"):
        parser_for_service = subparsers.add_parser(name, help=help_summary(name))
        parser_for_service.add_argument("service", choices=("mcp", "ngrok"))

    restart = subparsers.add_parser("restart", help=help_summary("restart"))
    restart.add_argument("service", choices=("mcp", "ngrok"))

    logs = subparsers.add_parser("logs", help=help_summary("logs"))
    logs.add_argument("service", nargs="?", choices=("review", "mcp", "ngrok"))

    subparsers.add_parser("open", help=help_summary("open"))
    subparsers.add_parser("mcp-url", help=help_summary("mcp-url"))
    subparsers.add_parser("copy-url", help=help_summary("copy-url"))
    subparsers.add_parser("paths", help=help_summary("paths"))
    subparsers.add_parser("storage", help=help_summary("storage"))
    cleanup = subparsers.add_parser("cleanup", help=help_summary("cleanup"))
    cleanup_mode = cleanup.add_mutually_exclusive_group()
    cleanup_mode.add_argument("--dry-run", action="store_true", help="Show cleanup candidates without deleting anything.")
    cleanup_mode.add_argument("--apply", action="store_true", help="Delete eligible cleanup candidates.")
    cleanup.add_argument("--older-than-days", type=int, default=None, help="Override age threshold for age-based cleanup candidates.")
    cleanup.add_argument("--include-backups", action="store_true", help="Include backups, command bundle file backups, and trash in cleanup candidates.")
    subparsers.add_parser("version", help=help_summary("version"))

    help_parser = subparsers.add_parser("help", help=help_summary("help"))
    help_parser.add_argument("topic", nargs="?", help="Command name to explain, such as start, cleanup, or copy-url.")
    language_group = help_parser.add_mutually_exclusive_group()
    language_group.add_argument("--lang", choices=("auto", "en", "ko"), default="auto", help="Help language. Defaults to locale auto-detection.")
    language_group.add_argument("--ko", action="store_const", const="ko", dest="lang", help="Show Korean help.")
    language_group.add_argument("--en", action="store_const", const="en", dest="lang", help="Show English help.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"setup", "configure"}:
        return run_dev_session("configure")
    if args.command in {"checklist", "doctor", "review", "start", "status", "stop"}:
        return run_dev_session(args.command)
    if args.command == "restart-session":
        return run_dev_session("restart-session")
    if args.command in {"start-service", "stop-service", "restart"}:
        return run_dev_session(args.command, args.service)
    if args.command == "logs":
        return run_dev_session("logs", args.service) if args.service else run_dev_session("logs")
    if args.command == "open":
        return open_review_dashboard()
    if args.command == "mcp-url":
        return print_mcp_url_preview()
    if args.command == "copy-url":
        return copy_mcp_url()
    if args.command == "paths":
        return supervisor.print_paths()
    if args.command == "storage":
        return supervisor.print_storage()
    if args.command == "cleanup":
        if args.older_than_days is not None and args.older_than_days < 1:
            print("[error] --older-than-days must be a positive integer.", file=sys.stderr)
            return 2
        return supervisor.cleanup_storage(
            apply=bool(args.apply),
            older_than_days=args.older_than_days,
            include_backups=bool(args.include_backups),
        )
    if args.command == "version":
        return print_version_info()
    if args.command == "help":
        return print_command_help(args.topic, language=args.lang)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
