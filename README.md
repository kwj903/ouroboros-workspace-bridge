# Workspace Terminal Bridge

ChatGPT에서 로컬 `~/workspace` 아래의 프로젝트를 안전하게 탐색하고, 수정하고, 검증하기 위한 개인용 MCP 서버입니다.

이 프로젝트의 목표는 ChatGPT와 대화하면서 로컬 프로젝트를 함께 진행할 수 있도록 다음 기능을 제공하는 것입니다.

- `~/workspace` 내부 파일/디렉터리 탐색
- UTF-8 텍스트 파일 읽기, 생성, 수정, append
- 파일/디렉터리 soft delete와 복구
- Git status/diff/add/commit
- 허용된 명령 프로필 실행
- operation/audit/backup/trash 기록
- patch 미리보기/적용
- Codex식 task/session 기록

## 현재 상태

이 서버는 개발용 MVP입니다.

기본 작업 루트는 다음 경로로 고정되어 있습니다.

```text
~/workspace
```

런타임 데이터는 다음 경로에 저장됩니다.

```text
~/.mcp_terminal_bridge/my-terminal-tool
```

런타임 데이터에는 audit log, backup, trash, operation record, task record가 포함됩니다.

## 프로젝트 구조

```text
my-terminal-tool/
├── data/
├── main.py
├── pyproject.toml
├── README.md
├── server.py
└── uv.lock
```

핵심 파일은 `server.py`입니다.

## 요구 사항

현재 확인된 개발 환경은 다음과 같습니다.

```text
macOS
Python 3.12+
uv
ngrok
ChatGPT Developer Mode App
```

Python 의존성은 `pyproject.toml` 기준입니다.

```toml
dependencies = [
    "mcp[cli]>=1.27.0",
    "pydantic>=2.13.3",
]
```

## 실행

프로젝트 디렉터리로 이동합니다.

```bash
cd ~/workspace/Custom-Tools/GPT-Tools/my-terminal-tool
```

서버를 실행합니다.

```bash
uv run python server.py
```

기본 주소는 다음과 같습니다.

```text
http://127.0.0.1:8787/mcp
```

환경 변수로 호스트와 포트를 바꿀 수 있습니다.

```bash
MCP_HOST=127.0.0.1 MCP_PORT=8787 uv run python server.py
```

## ngrok 연결

ngrok 고정 도메인을 사용하는 경우 예시는 다음과 같습니다.

```bash
ngrok http --url=iguana-dashing-tuna.ngrok-free.app 8787
```

ChatGPT 앱 설정의 MCP 서버 URL에는 다음 주소를 사용합니다.

```text
https://iguana-dashing-tuna.ngrok-free.app/mcp
```

서버 코드는 DNS rebinding 보호를 사용하며, 기본 허용 호스트에 `127.0.0.1`, `localhost`, `iguana-dashing-tuna.ngrok-free.app`를 포함합니다.

도메인을 바꾸려면 실행 시 `NGROK_HOST`를 지정합니다.

```bash
NGROK_HOST=your-domain.ngrok-free.app uv run python server.py
```

## ChatGPT 앱 갱신

`server.py`에 도구를 추가하거나 도구 스키마가 바뀌면 다음 순서로 갱신합니다.

1. MCP 서버 재시작
2. ChatGPT 앱 설정에서 새로 고침
3. 필요하면 새 채팅에서 앱 다시 선택
4. `workspace_info`로 도구 목록 확인

Inspector로 확인할 수도 있습니다.

```bash
npx -y @modelcontextprotocol/inspector --cli https://iguana-dashing-tuna.ngrok-free.app/mcp \
  --transport http \
  --method tools/call \
  --tool-name workspace_info
```

## 주요 도구

### 기본 탐색

```text
workspace_info
workspace_list
workspace_tree
workspace_find_files
workspace_search_text
workspace_read_file
workspace_read_many_files
workspace_project_snapshot
```

### 파일 변경

```text
workspace_create_directory
workspace_write_file
workspace_append_file
workspace_replace_text
workspace_preview_patch
workspace_apply_patch
```

큰 수정은 `workspace_apply_patch`를 우선 사용합니다. 여러 번의 작은 write 호출보다 한 번의 patch 적용이 안정적입니다.

기본 설정에서는 적용 결과를 가볍게 유지하기 위해 전체 diff를 반환하지 않습니다. 전체 diff가 필요하면 `workspace_git_diff`로 별도 조회합니다.

### 삭제/복구

```text
workspace_soft_delete
workspace_move_to_trash
workspace_restore_deleted
workspace_list_trash
```

삭제는 영구 삭제가 아니라 MCP trash로 이동하는 soft delete입니다.

### Git

```text
workspace_git_status
workspace_git_diff
workspace_git_add
workspace_git_commit
```

### 실행 프로필

```text
workspace_run_profile
```

현재 임의 shell 명령은 받지 않습니다. 허용된 프로필만 실행합니다.

예시 프로필:

```text
git_status
git_diff
uv_pytest
uv_ruff_check
uv_mypy
go_test
npm_test
npm_lint
```

### 기록/복구

```text
workspace_read_audit_log
workspace_get_operation
workspace_list_operations
workspace_list_backups
workspace_restore_backup
```

쓰기/삭제/patch 적용 같은 변경 작업은 operation 기록과 audit log를 남깁니다.

### Task/session

```text
workspace_task_start
workspace_task_status
workspace_task_log_step
workspace_task_update_plan
workspace_task_finish
workspace_list_tasks
```

긴 작업은 task를 시작하고, 계획/결정/수정/테스트/완료 내용을 기록하면서 진행합니다.

## 권장 작업 흐름

일반적인 개발 작업은 다음 순서로 진행합니다.

```text
1. workspace_task_start
2. workspace_project_snapshot
3. workspace_search_text / workspace_find_files
4. workspace_read_many_files
5. 수정 계획 정리
6. workspace_preview_patch
7. workspace_apply_patch
8. workspace_get_operation
9. workspace_git_diff
10. 테스트 또는 lint 실행
11. workspace_task_log_step
12. git add / commit
13. workspace_task_finish
```

이 흐름은 Codex식 작업 단위를 로컬 MCP 환경에 맞게 단순화한 것입니다.

## Patch 기반 수정

patch를 먼저 검증합니다.

```text
workspace_preview_patch
```

검증이 통과하면 적용합니다.

```text
workspace_apply_patch
```

`workspace_apply_patch`는 다음을 수행합니다.

1. patch 경로 안전성 검사
2. `git apply --check`
3. 기존 파일 backup
4. `git apply`
5. `git diff` 반환
6. operation/audit 기록

## 안전 모델

이 서버는 편의를 위해 만든 개발 도구이지만, 로컬 파일을 수정할 수 있으므로 신중하게 사용해야 합니다.

적용 중인 안전장치:

- 작업 루트는 `~/workspace`로 제한
- 절대 경로 차단
- `..` path traversal 차단
- `.ssh`, `.aws`, `.gnupg`, `.git`, `.venv`, `node_modules` 등 차단
- `.env`, key, pem, credential 계열 파일 차단
- 임의 shell command 미지원
- 허용된 command profile만 실행
- 파일 변경 전 backup 생성
- 삭제는 trash 이동 방식
- operation/audit 기록 저장

## 주의할 점

ngrok URL은 외부에서 접근 가능한 주소입니다. 작업하지 않을 때는 ngrok과 MCP 서버를 꺼두는 것을 권장합니다.

```text
작업 중:
  MCP 서버 실행
  ngrok 실행

작업 종료:
  ngrok 종료
  MCP 서버 종료
```

현재 인증은 ChatGPT 앱 설정과 ngrok URL 관리에 의존합니다. 장기 운영이 필요하면 OAuth, Access proxy, Tailscale, Cloudflare Access, 별도 gateway 구조를 검토해야 합니다.

## 문제 해결

### 406 Not Acceptable

브라우저에서 `/mcp`를 직접 열면 다음과 같은 응답이 나올 수 있습니다.

```text
Not Acceptable: Client must accept text/event-stream
```

MCP endpoint는 일반 웹 페이지가 아니므로 정상일 수 있습니다. Inspector 또는 ChatGPT 앱으로 확인합니다.

### 421 Misdirected Request

ngrok 도메인을 통해 접근할 때 host header가 허용 목록과 맞지 않으면 발생할 수 있습니다.

확인할 것:

- `NGROK_HOST`
- `transport_security.allowed_hosts`
- ngrok forwarding URL
- 서버 재시작 여부

### ChatGPT에서 새 도구가 안 보임

1. 서버 재시작
2. ChatGPT 앱 설정에서 새로 고침
3. 새 채팅에서 앱 다시 선택
4. Inspector CLI로 서버 도구가 보이는지 확인

### write/modify 승인 후 멈춤

ChatGPT UI의 승인 흐름이 간헐적으로 멈출 수 있습니다. 이 경우 같은 작업을 바로 반복하지 말고 다음을 확인합니다.

```text
workspace_get_operation
workspace_read_audit_log
workspace_git_status
workspace_git_diff
```

긴 수정은 `workspace_apply_patch`를 사용해 승인 횟수를 줄입니다.

## 검증 명령

문법 검사:

```bash
uv run python -m py_compile server.py
```

Git diff 품질 확인:

```bash
git diff --check
```

상태 확인:

```bash
git status --short --branch
```

도구 목록 확인:

```bash
npx -y @modelcontextprotocol/inspector --cli https://iguana-dashing-tuna.ngrok-free.app/mcp \
  --transport http \
  --method tools/call \
  --tool-name workspace_info
```

### Smoke check 스크립트

로컬 기본 검증은 다음 명령으로 실행합니다.

```bash
uv run python scripts/smoke_check.py
```

MCP 서버와 ngrok이 실행 중이면 Inspector까지 포함해서 확인할 수 있습니다.

```bash
uv run python scripts/smoke_check.py --mcp-url https://iguana-dashing-tuna.ngrok-free.app/mcp
```

또는 환경 변수로 지정할 수 있습니다.

```bash
MCP_URL=https://iguana-dashing-tuna.ngrok-free.app/mcp uv run python scripts/smoke_check.py
```

## 커밋 기준

기능 단위로 커밋합니다.

예시:

```text
Add workspace exploration MCP tools
Add patch preview and apply tools
Add task session tracking tools
Document workspace terminal bridge
```

커밋 전에는 다음을 확인합니다.

```bash
uv run python -m py_compile server.py
git diff --check
git status --short --branch
```

## 현재 개발 메모

이 프로젝트는 개인 로컬 개발 워크플로우를 위한 도구입니다. 최종 목표는 ChatGPT와 대화하면서 로컬 프로젝트를 안전하게 탐색하고, patch 단위로 수정하고, 테스트 결과와 작업 로그를 남기며 계속 이어서 개발할 수 있는 환경을 만드는 것입니다.
