# 로컬 세션 운영

이 문서는 Ouroboros Workspace Bridge를 로컬에서 실행하고 ChatGPT에 연결하는 운영 절차를 설명합니다.

## Repository root에서 시작

```bash
cd ouroboros-workspace-bridge
```

## 권장 흐름

공식 명령은 `uv run woojae ...`입니다. `scripts/dev_session.sh`와 `scripts/dev_session.ps1`은 기존 문서/자동화와 호환하기 위한 wrapper입니다.

처음 한 번 설정합니다.

```bash
uv run woojae setup
```

설정 과정에서 ChatGPT가 접근할 수 있는 `WORKSPACE_ROOT`와 기본 도움말 언어를 선택합니다. shell에 이미 설정된 `WORKSPACE_ROOT`, `MCP_ACCESS_TOKEN`, `NGROK_HOST`, `WOOJAE_HELP_LANG`은 runtime `session.env`보다 우선합니다.

프로젝트 명령어 도움말은 `uv run woojae help`로 확인할 수 있습니다. 한국어 도움말을 기본으로 보려면 setup 중 `Help language`를 `ko`로 저장하거나 `uv run woojae help --lang ko`를 사용하세요.

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

## Runtime 데이터 관리

설정, 로그, 승인 기록, 백업, 휴지통은 repository 밖의 runtime directory에 저장됩니다.

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

- `paths`는 project checkout, runtime data, session config, workspace root 위치를 보여줍니다.
- `storage`는 runtime data의 카테고리별 용량과 파일 수를 보여줍니다.
- `cleanup`은 기본적으로 dry-run입니다. 실제 삭제는 `uv run woojae cleanup --apply`를 명시한 경우에만 수행합니다.
- `session.json`, `session.env`, `intent_hmac_secret`, pending bundle, pid file은 보호 대상입니다.
- `backups`, `command_bundle_file_backups`, `trash`는 `--include-backups`를 추가해야 cleanup 후보에 포함됩니다.

실제 삭제 전에는 항상 `--dry-run` 결과를 먼저 확인하세요.

## Review UI

주요 페이지:

```text
http://127.0.0.1:8790/pending
http://127.0.0.1:8790/history
http://127.0.0.1:8790/servers
http://127.0.0.1:8790/servers?tab=processes
```

review UI는 ChatGPT가 만든 pending bundle을 로컬에서 확인하고 승인하는 곳입니다. 예상한 작은 변경만 승인하세요.

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
- `uv run woojae restart-session`은 review, MCP, ngrok을 새 코드로 재시작합니다.
- `uv run woojae status`에서 review와 mcp가 reachable인지 확인하세요.
- MCP tool 변경이 포함된 업데이트 후에는 ChatGPT app connector를 refresh/reconnect하세요.

## 프로세스 제어

일반 운영은 `woojae`를 사용합니다.

```bash
uv run woojae status
uv run woojae restart mcp
uv run woojae restart ngrok
uv run woojae restart-session
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

호환 wrapper도 같은 명령을 전달합니다. 새 문서와 자동화에서는 `uv run woojae ...`를 우선 사용하세요.

macOS/Linux:

```bash
scripts/dev_session.sh status
scripts/dev_session.sh restart-session
```

Windows PowerShell:

```powershell
.\scripts\dev_session.ps1 status
.\scripts\dev_session.ps1 restart-session
```

아래 script는 fallback/debug 용도로 직접 실행할 수 있습니다.

```bash
uv run woojae review
scripts/run_server.sh
scripts/run_ngrok.sh
```

## ChatGPT MCP 연결

1. 로컬 세션을 시작합니다.

```bash
uv run woojae start
```

2. review UI를 엽니다.

```bash
uv run woojae open
```

3. MCP URL을 clipboard에 복사하거나 URL 상태를 확인합니다.

```bash
uv run woojae copy-url
```

`copy-url`은 실제 URL을 clipboard에 복사하지만 token을 터미널에 출력하지 않습니다. macOS는 `pbcopy`, Linux는 `xclip`, Windows는 `clip`이 있으면 사용합니다. `uv run woojae mcp-url`은 redacted URL preview만 출력합니다.

MCP URL 형식:

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

실제 token 값은 문서, screenshot, chat, GitHub issue에 붙여넣거나 공유하지 마세요.

4. ChatGPT에서 app/connector 생성 화면을 엽니다.

UI는 바뀔 수 있으므로 settings, connector, apps 영역에서 custom app 또는 custom MCP connector 생성을 선택합니다.

5. app creation form을 채웁니다.

- 아이콘: 선택 사항입니다.
- 이름: `Ouroboros Workspace Bridge` 또는 `Woojae Workspace Bridge`
- 설명: `Local MCP bridge for approved workspace file and command operations.`
- MCP 서버 URL: `uv run woojae copy-url`로 복사한 URL을 붙여넣습니다.
- 인증: access token이 MCP URL query string에 이미 들어 있으므로 `No auth` 또는 이에 해당하는 항목을 선택합니다.
- 고급 OAuth 설정: UI가 요구하지 않는 한 비워둡니다.
- warning checkbox: custom MCP server는 데이터와 도구에 접근할 수 있으므로, 본인의 trusted local bridge라는 점을 이해한 뒤 체크하세요.

UI가 OAuth만 강제하는 경우 이 bridge는 그 모드를 사용하지 않을 수 있습니다. OAuth 없이 direct MCP URL을 넣는 방식을 선택하세요.

6. 생성 후 connector를 refresh/reconnect합니다.

도구가 보이는지 확인하고 local review page도 확인합니다.

```text
http://127.0.0.1:8790/pending
```

첫 테스트는 ChatGPT에게 대상 작업 디렉토리의 구성을 요약하고 어떤 종류의 프로젝트인지 설명해달라고 요청하세요. review UI에서는 예상한 bundle만 승인합니다.

redacted preview만 확인하려면:

```bash
uv run woojae mcp-url
```

## Temporary ngrok URL 주의

`NGROK_HOST`가 없으면 `woojae copy-url`이 동작하지 않을 수 있습니다. temporary ngrok URL은 재시작 후 바뀔 수 있어서 ChatGPT app의 MCP URL도 다시 수정해야 할 수 있습니다.

안정적으로 사용하려면 ngrok reserved domain을 만들고 `uv run woojae setup`에서 `NGROK_HOST`를 설정하세요.

## Approval mode

- Normal: 기본값입니다. 모든 pending bundle을 직접 승인합니다.
- Safe Auto: low-risk command-only bundle이 자동 승인될 수 있습니다. 일반 사용자에게는 Normal 또는 Safe Auto를 권장합니다.
- YOLO: 신뢰할 수 있는 짧은 세션에서만 쓰세요. 켜둔 채 오래 사용하지 마세요.

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
