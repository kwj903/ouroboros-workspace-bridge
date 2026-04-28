# 빠른 시작

Ouroboros Workspace Bridge를 처음 실행해서 ChatGPT에 연결하는 가장 짧은 절차입니다.

v0.1 권장 사용 방식은 repository checkout에서 `uv run woojae ...`를 실행하는 것입니다. 전역 설치는 이후 packaging 단계에서 다룹니다.

## 준비물

- macOS 권장
- Python 3.12+
- `uv`
- ngrok 계정과 ngrok CLI

## ngrok 준비

1. ngrok에 가입합니다.
2. ngrok CLI를 설치합니다.
3. ngrok CLI에 authtoken을 설정합니다.
4. reserved domain은 선택 사항입니다.

`NGROK_HOST`를 설정하지 않아도 첫 실행은 temporary URL mode로 가능합니다. 다만 `uv run woojae copy-url`은 고정 `NGROK_HOST`와 `MCP_ACCESS_TOKEN`이 모두 있어야 동작합니다.

토큰, ngrok authtoken, `.env` 값은 repository 파일에 넣지 마세요.

## 첫 설정

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
uv sync
uv run woojae setup
```

setup 중에는 ChatGPT가 접근할 수 있는 `WORKSPACE_ROOT`를 고릅니다. 이미 shell에 `WORKSPACE_ROOT`, `NGROK_HOST`, `MCP_ACCESS_TOKEN`이 설정되어 있으면 그 값이 runtime `session.env`보다 우선합니다.

## 시작

```bash
uv run woojae start
```

로컬 승인 UI:

```text
http://127.0.0.1:8790/pending
```

## ChatGPT 연결

redacted MCP URL 미리보기:

```bash
uv run woojae mcp-url
```

macOS clipboard에 실제 MCP URL 복사:

```bash
uv run woojae copy-url
```

`woojae mcp-url`은 실제 token을 출력하지 않습니다. `woojae copy-url`도 실제 URL을 출력하지 않고 redacted preview만 보여줍니다.

`NGROK_HOST`가 없으면 `woojae start` 후 ngrok 출력 또는 로그에서 temporary URL을 확인해야 합니다.

## Bundle 승인

ChatGPT가 파일 수정이나 명령 실행을 요청하면 pending bundle이 생성됩니다. review UI에서 내용을 확인한 뒤 예상한 작은 bundle만 승인하세요.

거절해야 하는 경우:

- 관련 없는 작업이 섞여 있음
- 예상하지 않은 파일을 수정함
- 너무 커서 검토하기 어려움
- 비밀값이 포함되어 있음

## 종료

```bash
uv run woojae stop
```
