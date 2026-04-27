# Workspace Terminal Bridge

ChatGPT에서 로컬 `~/workspace` 아래의 프로젝트를 안전하게 탐색하고, 수정하고, 검증하기 위한 개인용 MCP 서버입니다.

목표는 ChatGPT와 대화하면서 로컬 프로젝트를 함께 개발할 수 있도록 다음 흐름을 제공하는 것입니다.

- `~/workspace` 내부 파일/디렉터리 탐색
- UTF-8 텍스트 파일 읽기, 생성, 수정, append
- patch 미리보기/적용
- Git status/diff/add/commit
- 허용된 명령 프로필 실행
- command/action bundle 기반 로컬 승인 워크플로우
- 큰 텍스트 payload를 runtime에 저장하고 ref로 참조하는 안전한 대용량 수정 흐름
- operation/audit/backup/trash/task 기록

## 현재 상태

이 서버는 개인 로컬 개발용 MVP입니다.

기본 작업 루트는 다음 경로로 고정되어 있습니다.

```text
~/workspace
```

런타임 데이터는 다음 경로에 저장됩니다.

```text
~/.mcp_terminal_bridge/my-terminal-tool
```

런타임 데이터에는 audit log, backup, trash, operation record, task record, command bundle, text payload가 포함됩니다.

## 운영 원칙

이 프로젝트는 로컬 파일을 실제로 수정할 수 있으므로 다음 원칙을 지킵니다.

- 토큰 값은 README, 로그, 응답, `.env`에 넣지 않습니다.
- `MCP_ACCESS_TOKEN`은 개인 shell secrets에서 관리합니다. 예: `~/.dotfiles` 쪽 zsh secrets 파일
- 서버 실행 셸에서 secrets가 source되어 환경 변수로 들어온 상태를 전제로 합니다.
- 프로젝트 `.env`에 토큰을 만들거나 저장하지 않습니다.
- 읽기, 검색, git status, bundle status 확인은 MCP read tool로 직접 수행할 수 있습니다.
- 파일 생성/수정/명령 실행은 기본적으로 `workspace_stage_action_bundle` 또는 `workspace_stage_command_bundle`을 거쳐 로컬 승인 UI에서 적용합니다.
- 큰 텍스트는 action bundle 인자에 직접 넣지 않고 `workspace_stage_text_payload`로 runtime에 저장한 뒤 ref로 참조합니다.

## 프로젝트 구조

```text
my-terminal-tool/
├── data/
├── scripts/
│   ├── check_all.sh
│   ├── command_bundle_review_server.py
│   ├── command_bundle_runner.py
│   ├── command_bundle_watcher.py
│   ├── dev_session.sh
│   ├── run_ngrok.sh
│   ├── run_server.sh
│   └── smoke_check.py
├── terminal_bridge/
│   ├── __init__.py
│   ├── bundle_serialization.py
│   ├── bundles.py
│   ├── commands.py
│   ├── config.py
│   ├── models.py
│   ├── operations.py
│   ├── patches.py
│   ├── payloads.py
│   ├── safety.py
│   ├── storage.py
│   └── tasks.py
├── tests/
│   ├── test_refactored_helpers.py
│   ├── test_review_ui_helpers.py
│   └── test_safety.py
├── main.py
├── pyproject.toml
├── README.md
├── server.py
└── uv.lock
```

`server.py`는 FastMCP entrypoint와 MCP tool registration layer 역할을 담당합니다. 실제 helper 로직은 `terminal_bridge/` 패키지로 분리되어 있습니다.

`terminal_bridge/` 모듈 역할은 다음과 같습니다.

```text
config.py                런타임 경로, 제한값, 차단 이름, MCP 환경 설정
models.py                Pydantic response/input 모델
storage.py               JSON, timestamp, sha256 같은 작은 공통 helper
safety.py                workspace path/name safety helper
payloads.py              text payload ref 저장/검증/직렬화 helper
bundles.py               command bundle 저장, 조회, 상태 이동 helper
bundle_serialization.py  command/action bundle serialization helper
commands.py              argv 검증, command risk classification helper
patches.py               patch 경로 파싱과 git apply helper
tasks.py                 task/session record helper
operations.py            operation record helper
```

로컬 승인 UI와 bundle 실행기는 `scripts/` 아래에 있습니다.

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

## 개발 세션 운영

권장 작업 세션은 기존 MCP server/ngrok 실행 흐름을 유지하면서, 점검과 로컬 승인 UI 실행을 helper로 표준화합니다.

작업 전 점검:

```bash
scripts/dev_session.sh doctor
```

`MCP_ACCESS_TOKEN` 또는 `NGROK_HOST`가 현재 shell에 없으면 private runtime env 파일을 만들 수 있습니다.
이 파일은 프로젝트 밖의 `~/.mcp_terminal_bridge/my-terminal-tool/session.env`에 저장되며 helper script가 자동으로 source합니다.
프로젝트를 다른 위치에서 작업하더라도 이 runtime env 위치는 동일하게 사용됩니다. 필요하면 `MCP_TERMINAL_BRIDGE_RUNTIME_ROOT`로 runtime 위치를 바꿀 수 있습니다.
파일 권한은 `600`으로 제한합니다.

```bash
scripts/dev_session.sh configure
```

토큰 값은 입력 중 화면에 표시하지 않으며 README, 로그, git tracked 파일에 저장하지 않습니다.
`NGROK_HOST`는 사람마다 다를 수 있으므로 환경 변수 또는 `session.env`에서 관리합니다.

전체 로컬 세션 시작은 다음 한 명령을 권장합니다.

```bash
scripts/dev_session.sh start
```

이 명령은 review server, MCP server, ngrok을 백그라운드로 실행하고 `~/.mcp_terminal_bridge/my-terminal-tool/processes` 아래 pid/log 파일로 관리합니다. 같은 명령을 다시 실행하면 이미 살아 있는 supervisor-managed process를 재사용하고 중복 실행하지 않습니다.

세션 상태, 로그, 종료는 다음 명령으로 확인합니다.

```bash
scripts/dev_session.sh status
scripts/dev_session.sh logs [review|mcp|ngrok]
scripts/dev_session.sh stop
```

기존처럼 review server 하나만 foreground로 실행하려면 다음 명령을 사용할 수 있습니다.

```bash
scripts/dev_session.sh review
```

이 명령은 review server 하나를 foreground로 실행하고, 내부 embedded watcher가 pending bundle 감시와 알림을 담당합니다.
이미 8790 포트가 사용 중이면 기존 review server가 떠 있는 것으로 보고 시작을 중단하며, 기존 프로세스 종료 명령을 안내합니다.

MCP server와 ngrok을 수동으로 각각 실행해야 하는 fallback/debug 상황에서는 기존 script를 사용할 수 있습니다.

```bash
scripts/run_server.sh
scripts/run_ngrok.sh
```

로컬 review UI는 `승인 / 이력·결과 / 관리` 3개 주요 섹션으로 구성됩니다.
승인 대기 대시보드는 다음 주소를 한 번 열어두고 사용합니다.

```text
http://127.0.0.1:8790/pending
```

이력·결과 화면에서는 status별 count, 최근 실패 번들, bundle별 step/result/error 요약을 확인할 수 있습니다.

```text
http://127.0.0.1:8790/history
```

bundle 상세 페이지에서는 step별 status, stdout/stderr details, 실패 step, Raw result를 확인할 수 있습니다.
보기 전용 history 요약 API는 다음 endpoint입니다.

```text
http://127.0.0.1:8790/api/history-state
```

관리 섹션은 다음 주소에서 확인합니다.

```text
http://127.0.0.1:8790/servers
```

관리 섹션에는 개요, 서버, 프로세스, 연결, 환경, 로컬 도구, 진단 탭이 있으며 현재 단계에서는 모두 보기 전용입니다.
프로세스 탭에서는 `scripts/dev_session.sh start`가 관리하는 `review`, `mcp`, `ngrok` pid/alive/reachability/log path 상태를 확인할 수 있습니다. 이 화면은 상태만 읽으며 start/stop/restart를 실행하지 않습니다.
보기 전용 supervisor 요약 API는 다음 endpoint입니다.

```text
http://127.0.0.1:8790/api/supervisor-state
```

진단 탭에서는 최근 bundle 생성, 명령 실행, 상태 확인 같은 로컬 audit event 요약을 확인할 수 있습니다.
ChatGPT 도구 호출 뒤 응답이 끊겼을 때 직전 로컬 이벤트를 추적하는 데 사용합니다.
보기 전용 audit 요약 API는 다음 endpoint입니다.

```text
http://127.0.0.1:8790/api/audit-state
```

audit diagnostics는 token/secret 값을 노출하지 않는 안전한 요약만 표시합니다.

ChatGPT 앱 MCP URL 형식은 다음과 같습니다.

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

토큰 값은 README, 로그, 채팅 응답에 출력하지 않습니다.

embedded watcher는 기본적으로 macOS 알림 클릭 대상을 `/pending`으로 설정해 실행합니다.
`terminal-notifier`가 설치되어 있으면 클릭 가능한 macOS 알림을 사용할 수 있습니다.
알림 클릭 동작 기본값은 `focus`이며, Brave Browser, Google Chrome, Safari, Microsoft Edge에서 기존 review UI 탭을 찾아 포커스하고 없으면 새 탭으로 엽니다.

```bash
brew install terminal-notifier
```

기존 `terminal-notifier -open` 방식으로 되돌리려면 다음처럼 시작합니다.

```bash
BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION=open scripts/dev_session.sh review
```

`scripts/run_server.sh`, `scripts/run_ngrok.sh`, `scripts/dev_session.sh review`는 `session.env`가 있으면 자동으로 불러옵니다. 이미 shell 환경변수로 관리하는 경우에는 현재 shell의 값이 `session.env`보다 우선합니다. `session.env`는 빠진 값을 채우는 fallback으로 사용됩니다.

내장 watcher를 끄고 review server만 실행하려면 다음처럼 시작합니다.

```bash
BUNDLE_REVIEW_EMBEDDED_WATCHER=0 scripts/dev_session.sh review
```

기존 standalone watcher는 fallback/debug 용도로 유지합니다.

```bash
uv run python scripts/command_bundle_watcher.py
```

`server.py` 또는 MCP tool schema를 변경한 경우에는 MCP server를 재시작하고 ChatGPT 앱에서 Refresh해야 합니다.
review UI, watcher, README만 변경한 경우에는 보통 `scripts/dev_session.sh review` 세션만 재시작하면 되고 MCP server 재시작이나 ChatGPT 앱 Refresh는 필요하지 않습니다.

현재 `/servers`는 보기 전용 관리 페이지이며 start/stop/restart 버튼은 제공하지 않습니다.
프로세스 탭은 `scripts/dev_session.sh start`가 만든 pid/log 파일을 읽어 상태만 표시합니다.
실제 프로세스 제어는 아직 웹 UI에서 실행하지 않고 터미널의 `scripts/dev_session.sh start`, `status`, `logs`, `stop` 명령으로 수행합니다.

권장 실행 방식은 helper script를 사용하는 것입니다.

```bash
scripts/run_server.sh
```

`run_server.sh`는 `MCP_ACCESS_TOKEN`이 없는 경우 서버를 시작하지 않습니다. 토큰은 프로젝트 안에 저장하지 말고, 개인 shell secrets에서 source된 환경 변수로 주입합니다.

직접 실행할 수도 있습니다.

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

권장 실행 방식은 helper script입니다.

```bash
scripts/run_ngrok.sh
```

`run_ngrok.sh`는 `NGROK_HOST`를 우선 사용하고, 필요한 경우 예전 `NGROK_BASE_URL` 값을 fallback으로 사용할 수 있게 구성합니다.

직접 실행 예시는 다음과 같습니다.

```bash
ngrok http --url="$NGROK_HOST" "$MCP_PORT"
```

ChatGPT 앱 설정의 MCP 서버 URL은 다음 형식입니다.

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

실제 토큰 값은 README나 프로젝트 파일에 적지 않습니다. ChatGPT 앱 연결 설정과 실행 셸의 secrets에서만 관리합니다.

서버 코드는 DNS rebinding 보호를 사용하며, 기본 허용 호스트에 `127.0.0.1`, `localhost`, `NGROK_HOST`를 포함합니다.

## 연결 단위 토큰 인증

서버 시작 시 `MCP_ACCESS_TOKEN`이 설정되어 있으면 `/mcp` 요청에 토큰이 필요합니다.

토큰 전달 방식은 다음 중 하나입니다.

```text
Authorization: Bearer <TOKEN>
```

또는 ChatGPT 앱 URL query parameter입니다.

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

이 방식은 연결 설정 단계에서 토큰을 등록하는 구조입니다. 새 채팅마다 다시 인증하는 방식이 아닙니다.

토큰을 바꾸면 다음을 모두 갱신해야 합니다.

1. shell secrets의 `MCP_ACCESS_TOKEN`
2. MCP 서버 재시작
3. ChatGPT 앱 MCP URL
4. ChatGPT 앱 Refresh

주의: query token 방식은 간단하지만 URL 로그에 남을 수 있습니다. 개인 로컬 개발 MVP에서는 실용적이지만, 장기 운영이나 공유 환경에서는 OAuth, Access proxy, Tailscale, Cloudflare Access 같은 방식을 검토해야 합니다.

## ChatGPT 앱 갱신

`server.py`에 도구를 추가하거나 도구 스키마가 바뀌면 다음 순서로 갱신합니다.

1. MCP 서버 재시작
2. ChatGPT 앱 설정에서 Refresh
3. 필요하면 새 채팅에서 앱 다시 선택
4. `workspace_info`로 도구 목록 확인

Inspector로 확인할 수도 있습니다.

```bash
npx -y @modelcontextprotocol/inspector --cli "https://<NGROK_HOST>/mcp?access_token=$MCP_ACCESS_TOKEN" \
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

### 상태/patch 검증

```text
workspace_preview_patch
```

ChatGPT에 기본 노출되는 직접 도구는 읽기, 검색, 상태 확인, runtime 기록 확인 중심입니다.
파일 쓰기, 삭제, patch 적용, 임의 명령, install, `git add`, `git commit` 같은 위험 작업은 기본 MCP surface에 노출하지 않고 bundle로 staging한 뒤 로컬 review server에서 승인/실행합니다.

로컬 디버깅이 꼭 필요할 때만 `MCP_EXPOSE_DIRECT_MUTATION_TOOLS=1`로 direct mutation tools를 노출할 수 있습니다.
일반 사용 흐름에서는 설정하지 않습니다.

### Text payload ref

```text
workspace_stage_text_payload
```

큰 텍스트를 action bundle 인자에 직접 넣으면 ChatGPT 앱 승인 UI가 멈출 수 있습니다. 이를 피하기 위해 큰 텍스트는 먼저 MCP runtime에 chunk로 저장하고, action bundle에는 ref만 넣습니다.

저장 위치는 다음과 같습니다.

```text
~/.mcp_terminal_bridge/my-terminal-tool/text_payloads
```

기본 한도는 다음과 같습니다.

```text
chunk 최대 길이: 32,000 chars
payload 총 길이: 1,000,000 chars
```

지원 ref 필드:

```text
content_ref
old_text_ref
new_text_ref
```

예시 흐름:

```text
1. workspace_stage_text_payload로 큰 본문을 chunk 단위 저장
2. 반환된 payload_id 확인
3. workspace_stage_action_bundle의 write_file/append_file/replace_text에서 *_ref 필드 사용
4. 로컬 승인 UI에서 ref, 길이, chunk 수 확인
5. 승인 후 runner가 payload chunk를 조립해 실제 파일 작업 수행
```

### Command/action bundle

```text
workspace_stage_command_bundle
workspace_stage_action_bundle
workspace_stage_patch_bundle
workspace_command_bundle_status
workspace_list_command_bundles
workspace_cancel_command_bundle
```

지원 action type:

```text
command
write_file
append_file
replace_text
```

`workspace_stage_action_bundle`은 프로젝트 파일을 즉시 수정하지 않습니다. pending bundle을 runtime에 만들고, 로컬 승인 UI에서 승인한 뒤 runner가 적용합니다.
action bundle apply는 clean git worktree에서만 허용됩니다. `git status --porcelain`에 변경이 남아 있으면 apply를 거부하므로 먼저 변경을 commit/stash/revert해야 합니다.
apply 도중 action이 실패하면 이미 적용된 파일 action 변경을 rollback해서 repo가 partial apply 상태로 남지 않게 합니다.
ChatGPT가 생성한 코드 수정은 가능하면 `workspace_stage_patch_bundle`로 unified diff를 승인 UI에 올리는 흐름을 권장합니다.
터미널 명령, install/delete/run 명령, `git add`, `git commit`은 `workspace_stage_command_bundle`로 올린 뒤 로컬에서 승인합니다.

로컬 승인 UI:

```text
http://127.0.0.1:8790/pending
```

관련 스크립트:

```bash
uv run python scripts/command_bundle_review_server.py
uv run python scripts/command_bundle_watcher.py  # fallback/debug
uv run python scripts/command_bundle_runner.py list
uv run python scripts/command_bundle_runner.py preview <bundle_id>
uv run python scripts/command_bundle_runner.py apply <bundle_id>
```

권장 방식은 `scripts/dev_session.sh review`로 review server를 실행하는 것입니다.
review server의 embedded watcher가 pending bundle 감시, `/pending` dashboard 한 번 열기, macOS 알림 발송을 담당합니다.
`/pending`은 long polling으로 새 pending bundle이 생길 때만 갱신되며, 새 bundle마다 브라우저 탭을 계속 만들지 않습니다.
전체 이력과 실행 결과는 `http://127.0.0.1:8790/history`에서 확인합니다.
`/history` 상단에는 status별 count와 최근 실패 번들 링크가 표시되며, bundle 상세 페이지에서 step별 stdout/stderr와 실패 step을 확인합니다.
관리 정보는 `http://127.0.0.1:8790/servers`에서 보기 전용으로 확인합니다.
관리 > 프로세스 탭은 `scripts/dev_session.sh start`가 만든 pid/log 파일 기준으로 `review`, `mcp`, `ngrok` 상태를 표시합니다. 같은 요약은 `http://127.0.0.1:8790/api/supervisor-state`에서 JSON으로 확인할 수 있습니다.
관리 > 진단 탭에는 최근 로컬 작업 이벤트 표가 표시되고, 같은 요약은 `http://127.0.0.1:8790/api/audit-state`에서 JSON으로 확인할 수 있습니다.
이 화면은 ChatGPT 도구 호출 뒤 응답이 끊긴 경우 직전 로컬 MCP event를 추적하는 용도이며 token/secret 값은 표시하지 않습니다.

embedded watcher 기본값은 시작 시 `/pending` 대시보드를 한 번 여는 `dashboard_once` 모드입니다.
macOS 알림은 기본으로 켜져 있지만, 클릭 가능한 알림은 `terminal-notifier`가 설치되어 있을 때 동작합니다.
알림 클릭 동작은 기본적으로 `focus`입니다. 기존 review UI 탭이 있으면 해당 탭으로 포커스/이동하고, 없으면 새 탭을 엽니다.
기존 `terminal-notifier -open` 방식이 필요하면 `BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION=open`을 설정합니다.

```bash
brew install terminal-notifier
BUNDLE_REVIEW_EMBEDDED_WATCHER=0 scripts/dev_session.sh review
BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION=open scripts/dev_session.sh review
uv run python scripts/command_bundle_watcher.py
BUNDLE_WATCH_NOTIFY=0 uv run python scripts/command_bundle_watcher.py
BUNDLE_WATCH_NOTIFICATION_TARGET=bundle uv run python scripts/command_bundle_watcher.py
BUNDLE_WATCH_OPEN_MODE=bundle uv run python scripts/command_bundle_watcher.py
```

기본 알림 클릭 대상은 `/pending`입니다. 특정 bundle 상세 페이지로 바로 열고 싶으면 `BUNDLE_WATCH_NOTIFICATION_TARGET=bundle`을 설정합니다.
기존처럼 새 bundle마다 상세 탭을 자동으로 열고 싶으면 `BUNDLE_WATCH_OPEN_MODE=bundle`을 설정합니다.
브라우저를 전혀 열지 않으려면 `BUNDLE_WATCH_OPEN_MODE=none`을 설정합니다.
standalone `scripts/command_bundle_watcher.py`는 embedded watcher를 끈 상태에서 fallback/debug 용도로 직접 실행할 수 있습니다.

알림 클릭 focus helper는 수동으로도 확인할 수 있습니다.

```bash
uv run python scripts/focus_review_url.py http://127.0.0.1:8790/pending http://127.0.0.1:8790
```

### 삭제/복구

```text
workspace_list_trash
```

삭제/복구 같은 변경 작업은 기본 직접 도구가 아니라 command/action bundle 또는 로컬 fallback/debug 도구를 통해 처리합니다.

### Git

```text
workspace_git_status
workspace_git_diff
```

`git add`와 `git commit`은 기본 직접 도구가 아니라 command bundle approval workflow로 실행합니다.

### 명령 실행

```text
workspace_stage_command_bundle
```

테스트, lint, install, delete, run command처럼 프로젝트 상태를 바꿀 수 있거나 비용이 큰 명령은 command bundle로 staging하고 로컬 review server에서 한 번 클릭으로 승인/실행합니다.

### 기록/복구

```text
workspace_read_audit_log
workspace_get_operation
workspace_list_operations
workspace_list_backups
```

쓰기/삭제/patch 적용 같은 변경 작업은 로컬 runner가 수행하고, operation 기록과 audit log를 남깁니다.

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

일반적인 읽기 중심 작업은 다음 순서로 진행합니다.

```text
1. workspace_info
2. workspace_project_snapshot
3. workspace_search_text / workspace_find_files
4. workspace_read_file / workspace_read_many_files
5. workspace_git_status
```

파일 수정이 필요한 작업은 다음 흐름을 권장합니다.

```text
1. 수정 계획 정리
2. unified diff patch 생성
3. 필요한 경우 workspace_stage_text_payload로 patch 텍스트 저장
4. workspace_stage_patch_bundle에 patch_ref 전달
5. 로컬 승인 UI에서 확인 후 승인
6. workspace_command_bundle_status
7. workspace_git_diff
8. 테스트 또는 smoke check
9. git add / commit
```

작은 수동 파일 작업이나 명령 승인이 필요하면 기존 action/command bundle도 계속 사용할 수 있습니다.

```text
1. 수정 계획 정리
2. 필요한 경우 workspace_stage_text_payload로 큰 텍스트 저장
3. workspace_stage_action_bundle 또는 workspace_stage_command_bundle
4. 로컬 승인 UI에서 확인 후 승인
5. workspace_command_bundle_status
6. workspace_git_diff
7. 테스트 또는 smoke check
8. git add / commit
```

긴 작업은 task 기록을 함께 사용할 수 있습니다.

```text
1. workspace_task_start
2. 계획/결정/수정/검증 내용을 workspace_task_log_step으로 기록
3. 완료 시 workspace_task_finish
```

## Patch 기반 수정

ChatGPT가 만든 파일 수정은 direct write tool보다 patch bundle approval workflow를 우선 사용합니다.

```text
1. unified diff patch 생성
2. workspace_stage_text_payload로 patch 텍스트 저장
3. workspace_stage_patch_bundle(title, cwd, patch_ref) 호출로 pending bundle만 생성
4. 로컬 승인 UI에서 preview 확인
5. 승인 후 runner가 git apply --check, backup, git apply 수행
6. ChatGPT는 read-only 도구로 결과 검증
```

큰 patch는 tool call 본문에 직접 넣지 말고 `patch_ref`를 사용합니다.

```bash
uv run python scripts/command_bundle_runner.py preview <bundle_id>
uv run python scripts/command_bundle_runner.py apply <bundle_id>
```

`server.py` 또는 `terminal_bridge/*.py`를 변경한 뒤에는 MCP 서버를 재시작해야 새 tool/schema가 반영됩니다.

기존 direct write/apply/exec 도구는 fallback/internal/debug 용도로만 유지되며 기본 MCP surface에는 노출되지 않습니다.
patch를 read-only로 검증하려면 직접 노출되는 preview 도구를 사용합니다.

```text
workspace_preview_patch
```

적용이 필요하면 patch bundle을 staging합니다.

```text
workspace_stage_patch_bundle
```

로컬 runner가 승인 후 patch bundle에 대해 다음을 수행합니다.

1. patch 경로 안전성 검사
2. `git apply --check`
3. 기존 파일 backup
4. `git apply`
5. 필요하면 제한된 diff 반환
6. operation/audit 기록

큰 patch는 `workspace_stage_text_payload` + `workspace_stage_patch_bundle(patch_ref=...)` 흐름을 사용합니다.
기존 direct write/apply/exec tools는 `MCP_EXPOSE_DIRECT_MUTATION_TOOLS=1`을 설정한 로컬 디버그 상황에서만 직접 노출됩니다.

## 안전 모델

이 서버는 편의를 위해 만든 개발 도구이지만, 로컬 파일을 수정할 수 있으므로 신중하게 사용해야 합니다.

적용 중인 안전장치:

- 작업 루트는 `~/workspace`로 제한
- 절대 경로 차단
- `..` path traversal 차단
- `.ssh`, `.aws`, `.gnupg`, `.git`, `.venv`, `node_modules` 등 차단
- `.env`, key, pem, credential 계열 파일 차단
- 임의 shell command 직접 실행 제한
- 위험 명령은 차단 또는 approval required 처리
- 파일 변경 전 backup 생성
- 삭제는 trash 이동 방식
- operation/audit 기록 저장
- action bundle은 로컬 승인 전 프로젝트 파일을 수정하지 않음
- text payload는 runtime에 저장하고 ref로만 bundle에 연결 가능

## 주의할 점

ngrok URL은 외부에서 접근 가능한 주소입니다. 작업하지 않을 때는 ngrok과 MCP 서버를 꺼두는 것을 권장합니다.

```text
작업 중:
  MCP 서버 실행
  ngrok 실행
  필요하면 review server / watcher 실행

작업 종료:
  ngrok 종료
  MCP 서버 종료
  review server / watcher 종료
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

### 401 Unauthorized

토큰 인증이 켜져 있는데 요청에 토큰이 없거나 다를 때 발생합니다.

확인할 것:

- 실행 셸에 `MCP_ACCESS_TOKEN`이 들어왔는지
- ChatGPT 앱 MCP URL에 올바른 query token이 설정되어 있는지
- Authorization Bearer 방식으로 호출하는 경우 header가 맞는지
- 서버 재시작과 ChatGPT 앱 Refresh를 했는지

토큰 값은 터미널 출력, README, 채팅 응답에 노출하지 않습니다.

### ChatGPT에서 새 도구가 안 보임

1. 서버 재시작
2. ChatGPT 앱 설정에서 Refresh
3. 새 채팅에서 앱 다시 선택
4. Inspector CLI로 서버 도구가 보이는지 확인

### write/modify 승인 후 멈춤

ChatGPT 앱의 자체 MCP 승인 UI가 큰 tool call payload에서 멈출 수 있습니다.

이 경우 같은 큰 작업을 바로 반복하지 말고 다음을 확인합니다.

```text
workspace_list_command_bundles
workspace_command_bundle_status
workspace_git_status
workspace_git_diff
```

pending bundle이 생성되기 전에 앱 UI가 멈췄다면 로컬 승인 UI에도 나타나지 않을 수 있습니다. 긴 본문은 `workspace_stage_text_payload`로 chunk 저장 후 `content_ref`, `old_text_ref`, `new_text_ref`를 사용합니다.

## 검증 명령

문법 검사:

```bash
uv run python -m py_compile \
  server.py \
  terminal_bridge/*.py \
  scripts/command_bundle_runner.py \
  scripts/command_bundle_review_server.py \
  scripts/command_bundle_watcher.py \
  scripts/smoke_check.py \
  tests/*.py
```

유닛 테스트:

```bash
uv run python -m unittest discover -s tests
```

Smoke check:

```bash
uv run python scripts/smoke_check.py
```

전체 확인 helper:

```bash
scripts/check_all.sh
```

Git diff 품질 확인:

```bash
git diff --check
```

상태 확인:

```bash
git status --short --branch
```

MCP 서버와 ngrok이 실행 중이면 Inspector까지 포함해서 확인할 수 있습니다.

```bash
uv run python scripts/smoke_check.py --mcp-url "https://<NGROK_HOST>/mcp?access_token=$MCP_ACCESS_TOKEN"
```

또는 환경 변수로 지정할 수 있습니다.

```bash
MCP_URL="https://<NGROK_HOST>/mcp?access_token=$MCP_ACCESS_TOKEN" uv run python scripts/smoke_check.py
```

`scripts/smoke_check.py`는 `access_token`, `token`, `Authorization Bearer` 값을 출력에서 마스킹합니다. 실제 토큰 값을 테스트 fixture에 넣지 않습니다.

## 커밋 기준

기능 단위로 커밋합니다.

예시:

```text
Add workspace exploration MCP tools
Add patch preview and apply tools
Add command bundle approval workflow
Add text payload refs for action bundles
Document workspace terminal bridge
```

커밋 전에는 다음을 확인합니다.

```bash
uv run python -m py_compile \
  server.py \
  terminal_bridge/*.py \
  scripts/command_bundle_runner.py \
  scripts/command_bundle_review_server.py \
  scripts/command_bundle_watcher.py \
  scripts/smoke_check.py \
  tests/*.py
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
git status --short --branch
```

## 현재 개발 메모

이 프로젝트는 개인 로컬 개발 워크플로우를 위한 도구입니다. 최종 목표는 ChatGPT와 대화하면서 로컬 프로젝트를 안전하게 탐색하고, patch 또는 bundle 단위로 수정하고, 테스트 결과와 작업 로그를 남기며 계속 이어서 개발할 수 있는 환경을 만드는 것입니다.

현재 안정적인 수정 흐름은 다음과 같습니다.

```text
ChatGPT가 읽기/검색/status 확인
→ 큰 텍스트는 workspace_stage_text_payload로 runtime 저장
→ ChatGPT가 action bundle stage
→ 로컬 review server / watcher가 pending bundle 표시
→ 브라우저에서 승인하고 실행
→ runner가 payload ref를 조립해 파일 작업 수행
→ ChatGPT가 bundle status, git status, diff, 테스트 결과 확인
```
