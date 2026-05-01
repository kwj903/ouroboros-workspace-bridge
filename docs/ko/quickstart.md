# 빠른 시작

Ouroboros Workspace Bridge를 처음 실행해서 ChatGPT에 연결하는 가장 짧은 절차입니다.

권장 사용 방식은 repository checkout에서 `uv run woojae ...`를 실행하는 것입니다. `scripts/dev_session.sh`와 `scripts/dev_session.ps1`은 같은 CLI를 호출하는 호환 wrapper입니다.

## 준비물

- macOS: 기본 지원 환경
- Linux: Python supervisor 흐름 지원. 배포판별 clipboard/notification 동작은 다를 수 있음
- Windows: PowerShell 기반 Python supervisor 흐름 지원. ngrok, 방화벽, browser, clipboard 동작은 로컬 환경에 맞게 확인 필요
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

## 첫 설정: macOS/Linux

```bash
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
```

선택 사항으로 Bash helper를 사용할 수 있습니다.

```bash
./install.sh
uv run woojae setup
```

`install.sh`는 Bash 전용입니다. Windows PowerShell에서는 `install.ps1`을 사용하세요.

## 첫 설정: Windows PowerShell

```powershell
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
```

선택 사항으로 PowerShell helper를 사용할 수 있습니다.

```powershell
.\install.ps1
uv run woojae setup
```

setup 중에는 ChatGPT가 접근할 수 있는 `WORKSPACE_ROOT`와 도움말 언어(`Help language`)를 고릅니다. `Help language`를 `ko`로 저장하면 `uv run woojae help`가 기본적으로 한국어 설명을 표시합니다. 이미 shell에 `WORKSPACE_ROOT`, `NGROK_HOST`, `MCP_ACCESS_TOKEN`, `WOOJAE_HELP_LANG`이 설정되어 있으면 그 값이 runtime `session.env`보다 우선합니다.

## 시작

```bash
uv run woojae start
```

로컬 승인 UI:

```text
http://127.0.0.1:8790/pending
```

## ChatGPT 연결

1. 로컬 세션을 시작합니다.

```bash
uv run woojae start
```

2. 로컬 review UI를 엽니다.

```bash
uv run woojae open
```

3. MCP URL을 복사합니다.

```bash
uv run woojae copy-url
```

`copy-url`은 실제 MCP URL을 clipboard에 복사합니다. macOS는 `pbcopy`, Linux는 `xclip`, Windows는 `clip`이 있으면 사용합니다. `uv run woojae mcp-url`은 redacted URL preview만 출력합니다. 터미널에는 token을 출력하지 않습니다.

URL 형식은 다음과 같습니다.

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

실제 token을 문서, screenshot, chat, GitHub issue에 붙여넣거나 공유하지 마세요.

4. ChatGPT에서 app/connector 생성 화면을 엽니다.

ChatGPT UI는 바뀔 수 있으므로 일반적으로는 settings, connector, apps 영역에서 custom app 또는 custom MCP connector 생성을 선택합니다.

5. app creation form을 채웁니다.

- 아이콘: 선택 사항입니다.
- 이름: `Ouroboros Workspace Bridge` 또는 `Woojae Workspace Bridge`
- 설명: `Local MCP bridge for approved workspace file and command operations.`
- MCP 서버 URL: `uv run woojae copy-url`로 복사한 URL을 붙여넣습니다.
- 인증: access token이 MCP URL query string에 이미 포함되어 있으면 `No auth` 또는 이에 해당하는 항목을 선택합니다.
- 고급 OAuth 설정: 제품 UI가 요구하지 않는 한 비워둡니다.
- warning checkbox: custom MCP server는 데이터와 도구에 접근할 수 있습니다. 본인이 신뢰하는 local bridge라는 점과 위험을 이해한 뒤에만 체크하세요.

UI가 OAuth만 강제하는 경우 이 bridge는 그 모드를 사용하지 않을 수 있습니다. OAuth 없이 direct MCP URL을 넣을 수 있는 방식을 선택하세요.

6. 생성 후 connector를 refresh/reconnect합니다.

도구가 보이는지 확인하고, 로컬 review page도 열려 있는지 확인합니다.

```text
http://127.0.0.1:8790/pending
```

첫 테스트는 ChatGPT에게 harmless한 project status 또는 `git status` 확인을 요청하세요. 로컬 review UI에서는 예상한 bundle만 승인합니다.

redacted URL 미리보기만 보고 싶으면 다음 명령을 사용할 수 있습니다.

```bash
uv run woojae mcp-url
```

## Approval mode

- Normal: 기본값입니다. 모든 pending bundle을 직접 승인합니다.
- Safe Auto: low-risk command-only 확인 bundle은 자동 승인될 수 있습니다. 일반 사용자에게는 Normal 또는 Safe Auto를 권장합니다.
- YOLO: 신뢰할 수 있는 짧은 세션에서만 쓰세요. 켜둔 채로 오래 사용하지 마세요.

## Temporary ngrok URL 주의

`NGROK_HOST`가 없으면 `woojae copy-url`이 동작하지 않을 수 있습니다. temporary ngrok URL은 재시작 후 바뀔 수 있어서 ChatGPT app의 MCP URL도 다시 수정해야 할 수 있습니다.

가장 안정적인 사용을 위해 ngrok reserved domain을 만들고 `uv run woojae setup`에서 `NGROK_HOST`를 설정하는 것을 권장합니다.

## 기존 설치 업데이트

```bash
cd ouroboros-workspace-bridge
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

- `git pull`은 local checkout의 파일을 업데이트합니다.
- `uv sync`는 `pyproject.toml` 또는 lock file 변경이 있을 때 의존성을 갱신합니다.
- `uv run woojae restart-session`은 review, MCP, ngrok 세션을 새 코드로 재시작합니다.
- `uv run woojae status`에서 review와 mcp가 reachable인지 확인하세요.
- MCP tool이 바뀐 업데이트 후에는 ChatGPT app connector를 refresh/reconnect하세요.

## Bundle 승인

ChatGPT가 파일 수정이나 명령 실행을 요청하면 pending bundle이 생성됩니다. review UI에서 내용을 확인한 뒤 예상한 작은 bundle만 승인하세요.

거절해야 하는 경우:

- 관련 없는 작업이 섞여 있음
- 예상하지 않은 파일을 수정함
- 너무 커서 검토하기 어려움
- 비밀값이 포함되어 있음

## 라이선스

이 프로젝트는 **KwakWooJae Non-Commercial License 1.0**에 따라 비상업적 사용만 허용됩니다. 상업적 사용은 KwakWooJae의 사전 서면 허가가 필요합니다.

상업적 사용 문의: kwakwoojae@gmail.com

자세한 내용은 [LICENSE](../../LICENSE)를 참고하세요.

## 종료

```bash
uv run woojae stop
```
