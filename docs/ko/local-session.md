# 로컬 세션 운영

이 문서는 Ouroboros Workspace Bridge를 로컬에서 실행하고 ChatGPT에 연결하는 운영 절차를 설명합니다.

## Repository root에서 시작

```bash
cd ouroboros-workspace-bridge
```

## 권장 흐름

처음 한 번 설정합니다.

```bash
uv run woojae setup
```

설정 과정에서 ChatGPT가 접근할 수 있는 `WORKSPACE_ROOT`를 선택합니다. shell에 이미 설정된 `WORKSPACE_ROOT`, `MCP_ACCESS_TOKEN`, `NGROK_HOST`는 runtime `session.env`보다 우선합니다.

환경을 점검합니다.

```bash
uv run woojae doctor
```

전체 로컬 세션을 시작합니다.

```bash
uv run woojae start
```

상태 확인:

```bash
uv run woojae status
```

review UI 열기:

```bash
uv run woojae open
```

종료:

```bash
uv run woojae stop
```

## Runtime 환경

private runtime env 파일은 repository 밖에 저장됩니다.

```text
~/.mcp_terminal_bridge/my-terminal-tool/session.env
```

권장 권한:

```text
600
```

토큰 값은 문서, 로그, 테스트 fixture, screenshot, ChatGPT 메시지에 넣지 마세요.

`NGROK_HOST`는 선택 사항입니다. 없으면 `uv run woojae start`가 temporary URL mode로 ngrok을 실행합니다. `uv run woojae copy-url`은 `NGROK_HOST`와 `MCP_ACCESS_TOKEN`이 모두 있을 때만 동작합니다.

## Review UI

주요 페이지:

```text
http://127.0.0.1:8790/pending
http://127.0.0.1:8790/history
http://127.0.0.1:8790/servers
http://127.0.0.1:8790/servers?tab=processes
```

review UI는 ChatGPT가 만든 pending bundle을 로컬에서 확인하고 승인하는 곳입니다. 예상한 작은 변경만 승인하세요.

## 프로세스 제어

일반 운영은 `woojae`를 사용합니다.

```bash
uv run woojae status
uv run woojae restart mcp
uv run woojae restart ngrok
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

fallback/debug 용도로 script를 직접 실행할 수 있습니다.

```bash
scripts/dev_session.sh review
scripts/run_server.sh
scripts/run_ngrok.sh
```

## ChatGPT MCP 연결

MCP URL 형식:

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

실제 token 값은 출력하거나 문서에 남기지 마세요.

다음 경우 ChatGPT 앱의 MCP 연결을 refresh하세요.

- `server.py` 변경
- MCP tool schema 변경
- `MCP_ACCESS_TOKEN` 변경
- public ngrok host 변경

권장 순서:

```bash
uv run woojae restart mcp
uv run woojae status
```

## 안전한 bundle 흐름

1. ChatGPT가 pending bundle을 만듭니다.
2. review UI에서 내용을 확인합니다.
3. 작고 예상한 bundle만 승인합니다.
4. 승인 후 bundle status를 확인합니다.
5. 다음 작업으로 넘어갑니다.

파일 수정, 테스트, 커밋이 한 bundle에 섞여 있으면 승인하지 마세요.

문제 해결은 [문제 해결](troubleshooting.md)을 참고하세요.
