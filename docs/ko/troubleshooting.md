# 문제 해결

Ouroboros Workspace Bridge 로컬 운영 중 자주 만나는 문제와 복구 순서입니다.

명령은 repository root에서 실행합니다.

```bash
cd ouroboros-workspace-bridge
```

## 먼저 확인할 것

```bash
uv run terminalbridge status
uv run terminalbridge doctor
```

확인할 내용:

- `review`가 살아 있고 reachable인지
- `mcp`가 살아 있고 reachable인지
- ngrok 모드에서는 `ngrok`, Cloudflare 모드에서는 `cloudflared`가 관리되는지, 일반 external 모드에서는 connector가 수동 관리로 표시되는지
- `uv`가 설치되어 있는지
- token 값이 출력되지 않는지

## 첫 실행 성공 체크리스트

첫 설정 후에는 아래 순서로 확인하세요.

1. `uv run terminalbridge status`에서 review와 mcp가 reachable인지 확인합니다.
2. `http://127.0.0.1:8790/pending`이 로컬에서 열리는지 확인합니다.
3. `uv run terminalbridge copy-url` 또는 `uv run terminalbridge mcp-url`로 MCP URL 정보를 확인합니다.
4. ChatGPT custom app에 현재 MCP 서버 URL이 들어갔는지 확인합니다.
5. ChatGPT에게 대상 작업 디렉토리의 간단한 구성 요약을 요청했을 때 bundle이 생성되는지 확인합니다. Normal에서는 보통 `pending`으로 남고, Safe Auto/YOLO에서는 곧바로 `running` 또는 terminal state로 이동할 수 있습니다.
6. 현재 approval mode에 맞게 bundle을 처리하고 review/history에서 terminal result가 보이는지 확인합니다.
7. connector refresh/reconnect 후 기본 MCP surface가 `workspace_info`가 보고하는 canonical 31개 tool과 일치하는지 확인합니다.

어느 단계에서 실패했는지 먼저 좁힌 뒤, 그 단계부터 해결하세요.

## Review UI가 열리지 않음

증상:

- `http://127.0.0.1:8790/pending`이 열리지 않음
- `/servers` 또는 `/history`가 응답하지 않음

확인:

```bash
uv run terminalbridge status
uv run woojae logs review
```

복구:

```bash
uv run terminalbridge restart
```

그래도 안 되면:

```bash
uv run terminalbridge stop
uv run terminalbridge start
uv run terminalbridge status
```

## MCP server가 unreachable

증상:

- ChatGPT MCP call 실패
- `/servers?tab=processes`에서 MCP reachable이 `no`
- `uv run terminalbridge status`에서 `mcp alive=no` 또는 `reachable=no`

확인:

```bash
uv run terminalbridge status
uv run woojae logs mcp
```

복구:

```bash
uv run woojae restart mcp
uv run terminalbridge status
```

`server.py` 또는 MCP tool schema가 바뀌었다면 ChatGPT 앱에서 MCP 연결도 refresh하세요.

## ChatGPT tool로 세션 재시작을 실행했을 때 연결이 끊김

증상:

- ChatGPT가 `uv run terminalbridge restart` 같은 세션 재시작 bundle을 만든 뒤 MCP 연결이 끊깁니다.
- review UI에 재시작 bundle이 pending, rejected, failed 이력으로 남아 보일 수 있습니다.

이것은 대부분 정상적인 부작용입니다. MCP 서버가 자기 자신을 재시작하면 현재 ChatGPT tool connection도 함께 끊길 수 있습니다.

권장 복구:

```bash
uv run terminalbridge status
uv run terminalbridge start
# 또는
uv run terminalbridge restart
```

그 다음 ChatGPT 앱에서 MCP 연결을 refresh하고, ChatGPT에서 `workspace_transport_probe` 또는 `workspace_git_status` 같은 읽기 도구로 연결을 확인합니다.

권장 운영 방식:

- 전체 로컬 세션 재시작은 가능하면 터미널에서 직접 실행합니다. 선택한 관리형 ngrok 또는 Cloudflare connector가 자동으로 포함됩니다.
- ChatGPT tool proposal로 서버 자체를 재시작하는 방식은 연결이 끊겨 상태 반영이 꼬일 수 있으므로 디버깅 목적이 아니면 피합니다.
- rejected 또는 failed로 남은 재시작 bundle은 이미 처리된 이력일 수 있으므로 `/history`와 bundle status를 함께 확인합니다.

## Cloudflare 또는 external 도메인 연결 문제

증상:

- `PUBLIC_ACCESS_MODE=external`인데 공개 endpoint가 로컬 MCP 서버로 연결되지 않음
- `uv run terminalbridge status`에서는 review와 MCP가 정상인데 ChatGPT 연결이 실패함

확인:

```bash
uv run terminalbridge doctor
uv run terminalbridge status
uv run terminalbridge logs mcp
uv run terminalbridge logs cloudflared
uv run terminalbridge mcp-url
```

관리형 Cloudflare 모드에서는 사용자의 config path와 tunnel 이름이 정확하고 `cloudflared`가 살아 있는지 확인합니다. 일반 external 모드에서는 proxy 또는 connector를 별도로 시작합니다. 두 경우 모두 공개 hostname을 `http://127.0.0.1:8787`에만 연결하고 review UI는 비공개로 유지하며 다른 컴퓨터의 replica connector를 종료하세요. 자세한 내용은 [공개 연결 모드](public-access.md)를 확인하세요.

## ngrok 연결 문제

증상:

- public MCP endpoint가 동작하지 않음
- ChatGPT가 ngrok URL을 통해 local MCP server에 연결하지 못함
- ngrok log에 tunnel/account 오류가 있음

확인:

```bash
uv run terminalbridge status
uv run woojae logs ngrok
```

복구:

```bash
uv run woojae restart ngrok
uv run terminalbridge status
```

`NGROK_HOST`는 temporary URL mode에서는 선택 사항입니다. 하지만 `uv run terminalbridge copy-url`은 고정 `NGROK_HOST`와 `MCP_ACCESS_TOKEN`이 필요합니다.

## Bundle이 pending에 멈춤

확인할 페이지:

```text
http://127.0.0.1:8790/pending
http://127.0.0.1:8790/history
```

ChatGPT에서 확인할 도구:

```text
workspace_list_command_bundles
workspace_command_bundle_status <bundle_id>
```

복구:

- 예상한 작은 bundle이면 승인합니다.
- 너무 크거나 관련 없는 작업이 섞였으면 reject/cancel합니다.
- 승인/거절 후 status를 다시 확인합니다.

## 로컬 알림이 뜨지 않음

알림 도구는 선택 사항입니다. 알림이 없어도 review UI와 bundle 승인 흐름은 계속 사용할 수 있습니다.

```bash
uv run terminalbridge doctor
```

- macOS: `terminal-notifier`가 있으면 클릭 가능한 알림을 사용하고, 설정에 따라 `osascript` fallback을 사용할 수 있습니다.
- Linux: `notify-send`가 있으면 desktop notification을 보냅니다. URL 열기는 `xdg-open` 또는 Python browser fallback을 사용합니다.
- Windows: PowerShell/BurntToast가 가능하면 알림을 시도합니다. 실패해도 watcher는 계속 동작합니다.

## Bundle 실패

확인:

```text
workspace_command_bundle_status <bundle_id>
```

살펴볼 항목:

- failed step name
- exit code
- stdout/stderr
- rollback 또는 backup 정보

복구 순서:

1. 같은 큰 요청을 바로 반복하지 않습니다.
2. `git status`를 확인합니다.
3. 원인을 하나씩 작은 bundle로 고칩니다.
4. 실패한 검증 명령만 먼저 다시 실행합니다.

## Runtime 데이터가 계속 쌓임

증상:

- `~/.mcp_terminal_bridge/my-terminal-tool` 용량이 커짐
- 오래된 bundle, tool call, backup, trash 기록이 많아짐
- runtime 경로가 어디인지 헷갈림

확인:

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

복구:

- 먼저 `cleanup --dry-run`으로 삭제 후보만 확인합니다.
- 후보가 안전한지 확인한 뒤에만 `uv run woojae cleanup --apply`를 실행합니다.
- 백업/휴지통까지 후보에 포함하려면 `--include-backups`를 명시합니다.
- `session.json`, `session.env`, `intent_hmac_secret`, pending bundle, pid file은 보호됩니다.

## PID file stale

증상:

- `status`에 `alive=stale` 표시
- 실제 프로세스는 없는데 pid file이 남아 있음

확인:

```bash
uv run terminalbridge status
```

복구:

```bash
uv run woojae restart mcp
uv run woojae restart ngrok
```

review 관련 stale 상태는 전체 세션 재시작이 더 단순합니다.

```bash
uv run terminalbridge restart
```

## ChatGPT 응답이 끊겼지만 bundle이 생겼을 수 있음

먼저 다시 요청하지 말고 확인합니다.

```text
workspace_list_command_bundles
workspace_git_status
```

새 bundle이 있으면:

- review UI에서 확인
- 안전하면 승인
- 애매하면 reject/cancel

상태가 명확해진 뒤 다음 작은 bundle을 만드세요.
