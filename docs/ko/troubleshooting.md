# 문제 해결

Ouroboros Workspace Bridge 로컬 운영 중 자주 만나는 문제와 복구 순서입니다.

명령은 repository root에서 실행합니다.

```bash
cd ouroboros-workspace-bridge
```

## 먼저 확인할 것

```bash
uv run woojae status
uv run woojae doctor
```

확인할 내용:

- `review`가 살아 있고 reachable인지
- `mcp`가 살아 있고 reachable인지
- `ngrok` 프로세스와 로그가 있는지
- `uv`가 설치되어 있는지
- token 값이 출력되지 않는지

## Review UI가 열리지 않음

증상:

- `http://127.0.0.1:8790/pending`이 열리지 않음
- `/servers` 또는 `/history`가 응답하지 않음

확인:

```bash
uv run woojae status
uv run woojae logs review
```

복구:

```bash
scripts/dev_session.sh restart-session
```

그래도 안 되면:

```bash
uv run woojae stop
uv run woojae start
uv run woojae status
```

## MCP server가 unreachable

증상:

- ChatGPT MCP call 실패
- `/servers?tab=processes`에서 MCP reachable이 `no`
- `uv run woojae status`에서 `mcp alive=no` 또는 `reachable=no`

확인:

```bash
uv run woojae status
uv run woojae logs mcp
```

복구:

```bash
uv run woojae restart mcp
uv run woojae status
```

`server.py` 또는 MCP tool schema가 바뀌었다면 ChatGPT 앱에서 MCP 연결도 refresh하세요.

## ngrok 연결 문제

증상:

- public MCP endpoint가 동작하지 않음
- ChatGPT가 ngrok URL을 통해 local MCP server에 연결하지 못함
- ngrok log에 tunnel/account 오류가 있음

확인:

```bash
uv run woojae status
uv run woojae logs ngrok
```

복구:

```bash
uv run woojae restart ngrok
uv run woojae status
```

`NGROK_HOST`는 temporary URL mode에서는 선택 사항입니다. 하지만 `uv run woojae copy-url`은 고정 `NGROK_HOST`와 `MCP_ACCESS_TOKEN`이 필요합니다.

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

## PID file stale

증상:

- `status`에 `alive=stale` 표시
- 실제 프로세스는 없는데 pid file이 남아 있음

확인:

```bash
uv run woojae status
```

복구:

```bash
uv run woojae restart mcp
uv run woojae restart ngrok
```

review 관련 stale 상태는 전체 세션 재시작이 더 단순합니다.

```bash
scripts/dev_session.sh restart-session
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
