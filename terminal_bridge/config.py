from __future__ import annotations

import os
import shlex
from pathlib import Path


# 기본 런타임 저장소 위치입니다.
# 승인 번들, 감사 로그, 백업, 작업 기록 같은 로컬 실행 상태가 이 아래에 저장됩니다.
DEFAULT_RUNTIME_ROOT = (Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool").resolve()


def _runtime_root() -> Path:
    # MCP_TERMINAL_BRIDGE_RUNTIME_ROOT 환경변수가 있으면 기본 런타임 위치 대신 사용합니다.
    # 테스트나 별도 세션을 격리할 때 이 값을 바꿀 수 있습니다.
    return Path(os.getenv("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))).expanduser().resolve()


def _session_env_value(name: str) -> str | None:
    # 런타임 루트의 session.env에서 저장된 세션 환경변수를 읽습니다.
    # 쉘 환경변수가 없을 때 WORKSPACE_ROOT 같은 값을 복구하는 fallback 용도입니다.
    session_env = _runtime_root() / "session.env"
    if not session_env.exists():
        return None

    try:
        lines = session_env.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    prefixes = (f"export {name}=", f"{name}=")
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(prefixes):
            continue

        assignment = stripped.removeprefix("export ")
        try:
            parts = shlex.split(assignment, comments=False, posix=True)
        except ValueError:
            continue
        if not parts or not parts[0].startswith(f"{name}="):
            continue
        return parts[0].split("=", 1)[1]

    return None


def _workspace_root_value() -> str:
    # 로컬 작업 허용 범위의 루트 경로입니다.
    # 우선순위: 현재 쉘의 WORKSPACE_ROOT > session.env의 WORKSPACE_ROOT > ~/workspace
    return os.getenv("WORKSPACE_ROOT") or _session_env_value("WORKSPACE_ROOT") or str(Path.home() / "workspace")


def _resolve_workspace_root() -> Path:
    root = Path(_workspace_root_value()).expanduser().resolve(strict=False)
    dangerous_roots = {
        Path("/").resolve(strict=False),
        Path("/System").resolve(strict=False),
        Path("/Library").resolve(strict=False),
        Path("/private").resolve(strict=False),
        Path("/etc").resolve(strict=False),
        Path("/usr").resolve(strict=False),
        Path("/bin").resolve(strict=False),
        Path("/sbin").resolve(strict=False),
    }
    if root in dangerous_roots:
        raise ValueError(f"Unsafe WORKSPACE_ROOT is not allowed: {root}")
    return root


def _normalize_ngrok_host(value: str) -> str:
    # ngrok URL 또는 host 입력에서 scheme/path/query를 제거해 host만 남깁니다.
    # MCP transport 보안 설정의 allowed_hosts/allowed_origins 계산에 사용됩니다.
    host = value.strip()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host


# 실제 로컬 작업을 허용할 최상위 디렉터리입니다.
# 읽기, 검색, proposal 생성, 명령 실행 cwd 검증은 이 경계 안에서만 허용됩니다.
WORKSPACE_ROOT = _resolve_workspace_root()

# 이 MCP 앱 자체의 프로젝트 루트입니다. server.py, scripts/, terminal_bridge/ 위치 계산에 사용됩니다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 런타임 데이터 루트입니다. Git 저장소에 들어가지 않는 로컬 상태 파일들이 저장됩니다.
RUNTIME_ROOT = _runtime_root()

# 감사 로그 파일입니다. 주요 MCP 호출, proposal 생성, 명령 실행 결과 추적에 사용됩니다.
AUDIT_LOG = RUNTIME_ROOT / "audit.jsonl"

# 파일 변경 전 백업을 저장하는 위치입니다. file write/replace/patch/restore 계열에서 사용됩니다.
BACKUP_DIR = RUNTIME_ROOT / "backups"

# 삭제 대신 이동하는 휴지통 위치입니다. 안전한 삭제/복구 흐름에 사용됩니다.
TRASH_DIR = RUNTIME_ROOT / "trash"

# 장기 operation 상태를 저장하는 위치입니다. 작업 시작/완료/실패 상태 조회에 사용됩니다.
OPERATION_DIR = RUNTIME_ROOT / "operations"

# Codex-style task 기록 저장 위치입니다. 작업 계획, 진행 로그, 완료 상태가 저장됩니다.
TASK_DIR = RUNTIME_ROOT / "tasks"

# task-workspace 모드의 격리 git worktree들이 생성되는 위치입니다.
TASK_WORKSPACES_DIR = RUNTIME_ROOT / "task_workspaces"

# 긴 텍스트 payload chunk를 저장하는 위치입니다. 큰 patch/content를 ref로 넘길 때 사용됩니다.
TEXT_PAYLOAD_DIR = RUNTIME_ROOT / "text_payloads"

# MCP tool call 계측 기록 저장 위치입니다. 최근 tool 호출 상태 조회와 복구에 사용됩니다.
TOOL_CALL_DIR = RUNTIME_ROOT / "tool_calls"

# bundle 완료 후 handoff 요약을 저장하는 위치입니다. 다음 세션/다른 클라이언트 복구에 사용됩니다.
HANDOFF_DIR = RUNTIME_ROOT / "handoffs"

# local /pending 승인 번들의 최상위 저장 위치입니다.
COMMAND_BUNDLES_DIR = RUNTIME_ROOT / "command_bundles"

# 사용자 승인 대기 중인 번들 저장 위치입니다.
COMMAND_BUNDLE_PENDING_DIR = COMMAND_BUNDLES_DIR / "pending"

# 정상 적용 완료된 번들 저장 위치입니다.
COMMAND_BUNDLE_APPLIED_DIR = COMMAND_BUNDLES_DIR / "applied"

# 사용자가 거절한 번들 저장 위치입니다.
COMMAND_BUNDLE_REJECTED_DIR = COMMAND_BUNDLES_DIR / "rejected"

# 실행 또는 적용 중 실패한 번들 저장 위치입니다.
COMMAND_BUNDLE_FAILED_DIR = COMMAND_BUNDLES_DIR / "failed"

# 단일 파일 읽기 응답의 최대 문자 수입니다. 너무 크게 잡으면 응답이 무거워집니다.
MAX_READ_CHARS = 320_000

# file write/replace 계열에서 한 번에 받을 수 있는 텍스트 최대 문자 수입니다.
MAX_WRITE_CHARS = 400_000

# tree/list 계열에서 반환할 수 있는 최대 항목 수입니다.
MAX_TREE_ENTRIES = 800

# 명령 stdout 저장/반환 최대 문자 수입니다. 긴 로그는 이 값 기준으로 잘립니다.
MAX_STDOUT_CHARS = 120_000

# 명령 stderr 저장/반환 최대 문자 수입니다. 실패 로그가 너무 길 때 이 값 기준으로 잘립니다.
MAX_STDERR_CHARS = 80_000

# text payload 한 chunk의 최대 문자 수입니다. 큰 patch/content를 나눠 저장할 때 사용됩니다.
TEXT_PAYLOAD_CHUNK_MAX_CHARS = 64_000

# text payload 전체 조합 결과의 최대 문자 수입니다.
TEXT_PAYLOAD_MAX_TOTAL_CHARS = 2_000_000

# 명령 argv 항목 하나가 가질 수 있는 최대 문자 수입니다.
MAX_EXEC_ARG_CHARS = 64_000

# 명령 argv 전체 문자열 합산 최대 문자 수입니다.
MAX_EXEC_ARGV_TOTAL_CHARS = 256_000

# 명령 argv 항목 개수 최대값입니다. 너무 긴 명령 배열을 차단합니다.
MAX_EXEC_ARGV_ITEMS = 80

# read_many_files에서 파일 하나당 읽을 수 있는 최대 문자 수입니다.
MAX_READ_MANY_FILE_CHARS = 160_000

# read_many_files 전체 응답의 최대 문자 수입니다.
MAX_READ_MANY_TOTAL_CHARS = 800_000

# find_files 결과의 최대 항목 수입니다.
MAX_FIND_ENTRIES = 800

# search_text 결과의 최대 match 수입니다.
MAX_SEARCH_MATCHES = 800

# search_text가 파일 하나를 검색할 때 읽을 수 있는 최대 바이트 수입니다.
MAX_SEARCH_FILE_BYTES = 1_000_000

# diff/patch 미리보기에서 반환할 수 있는 최대 문자 수입니다.
MAX_DIFF_PREVIEW_CHARS = 120_000

# diff/patch 미리보기 기본 문자 수입니다. 별도 지정이 없으면 이 값으로 잘립니다.
DEFAULT_DIFF_PREVIEW_CHARS = 20_000

# 승인된 명령 step 하나가 실행될 수 있는 최대 시간(초)입니다.
# 오래 걸리는 테스트/빌드가 자주 timeout 되면 이 값을 올릴 수 있지만, 멈춘 명령 감지도 늦어집니다.
MAX_COMMAND_TIMEOUT_SECONDS = 900

# public *_and_wait MCP 도구가 승인 번들의 상태 변화를 기다리는 시간 설정(초)입니다.
# 현재 runner 구조에서는 사용자 승인 대기 시간과 승인된 작업의 완료 대기 시간이 함께 포함됩니다.
# 기본값을 올리면 긴 테스트/빌드/graphify 작업이 끝날 때까지 GPT가 더 오래 기다릴 수 있습니다.
MIN_BUNDLE_WAIT_SECONDS = 1
DEFAULT_BUNDLE_WAIT_SECONDS = 300
MAX_BUNDLE_WAIT_SECONDS = 900

# *_and_wait 도구가 기다리는 동안 번들 상태를 다시 확인하는 간격(초)입니다.
# 낮추면 승인 직후 더 빨리 반응하지만 로컬 상태 조회가 잦아집니다.
MIN_BUNDLE_POLL_INTERVAL_SECONDS = 0.2
DEFAULT_BUNDLE_POLL_INTERVAL_SECONDS = 1.0
MAX_BUNDLE_POLL_INTERVAL_SECONDS = 5.0

# 파일/patch/action 경로에서 접근을 막을 디렉터리 이름입니다.
# 보안 자격증명, git 내부 데이터처럼 AI가 직접 건드리면 위험한 영역을 차단합니다.
BLOCKED_DIR_NAMES = {
    ".aws",
    ".gnupg",
    ".git",
}

# 직접 읽기/쓰기/patch 대상에서 차단할 파일명 패턴입니다.
# `.env`는 비밀값이 들어갈 가능성이 높아서 기본 차단합니다.
BLOCKED_FILE_PATTERNS = [
    ".env",
]

# 안전 명령 분류에서 낮은 위험으로 허용할 수 있는 보조 플래그 목록입니다.
# 테스트/검색/출력 제어용 플래그처럼 파일 시스템을 크게 변경하지 않는 값들입니다.
SAFE_ARG_FLAGS = {
    "-q",
    "-v",
    "-x",
    "-s",
    "--maxfail=1",
    "--tb=short",
    "--tb=long",
    "--disable-warnings",
    "--no-header",
    "--no-summary",
}

# 항상 차단할 실행 파일 목록입니다.
# 관리자 권한, 디스크 포맷, 시스템 계정 전환처럼 로컬 환경을 크게 손상시킬 수 있는 명령입니다.
BLOCKED_EXECUTABLES = {
    "sudo",
    "su",
    "diskutil",
    "dd",
    "mkfs",
}

# 실행 전 사용자 승인이 필요한 실행 파일 목록입니다.
# 셸, 네트워크, 패키지 설치, 원격 접속, 파일 권한 변경처럼 부작용 가능성이 있는 명령입니다.
APPROVAL_REQUIRED_EXECUTABLES = {
    "bash",
    "sh",
    "zsh",
    "curl",
    "chmod",
    "chown",
    "killall",
    "launchctl",
    "osascript",
    "pkill",
    "rm",
    "rsync",
    "scp",
    "sftp",
    "ssh",
    "wget",
    "pip",
    "pip3",
    "npm",
    "pnpm",
    "yarn",
}

# 명령 문자열/argv에서 발견되면 승인 대상으로 분류할 위험 패턴입니다.
# git 상태 변경, 패키지 설치, 삭제/권한 변경 계열을 local /pending review로 보냅니다.
APPROVAL_REQUIRED_PATTERNS = {
    "rm",
    "chmod",
    "chown",
    "git clean",
    "git reset",
    "git push",
    "git checkout",
    "git switch",
    "uv add",
    "uv sync",
    "uv pip",
    "npm install",
    "npm add",
}


# MCP 서버가 바인딩할 호스트입니다. 기본값은 로컬 루프백입니다.
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")

# MCP 서버 포트입니다. 로컬 connector/ngrok 연결 대상 포트로 사용됩니다.
MCP_PORT = int(os.getenv("MCP_PORT", "8787"))

# ngrok 고정 도메인 또는 base URL에서 추출한 host입니다.
# 외부 ChatGPT connector가 로컬 MCP 서버에 접근할 때 transport 보안 허용 목록에 사용됩니다.
NGROK_HOST = _normalize_ngrok_host(os.getenv("NGROK_HOST") or os.getenv("NGROK_BASE_URL", ""))

# MCP 접근 토큰입니다. 외부 connector 요청을 인증할 때 사용되며, 값 자체를 로그/출력에 노출하면 안 됩니다.
MCP_ACCESS_TOKEN = os.getenv("MCP_ACCESS_TOKEN")

# 직접 변경 도구 노출 스위치입니다.
# 기본값은 False이며, public schema에는 review-gated proposal 도구를 우선 노출합니다.
# 정말 필요한 개발/디버그 상황에서만 MCP_EXPOSE_DIRECT_MUTATION_TOOLS=1로 켭니다.
MCP_EXPOSE_DIRECT_MUTATION_TOOLS = os.getenv("MCP_EXPOSE_DIRECT_MUTATION_TOOLS") == "1"
