# 로컬 세션 운영

이 문서는 Ouroboros Workspace Bridge를 로컬에서 실행하고 ChatGPT에 연결하는 운영 절차를 설명합니다.

## Repository root에서 시작

```bash
cd ouroboros-workspace-bridge
```

## 권장 흐름

일반적인 전체 연결 스택 운영에는 `uv run terminalbridge ...`를 사용합니다. `uv run woojae ...`는 저수준 진단·업데이트용으로 유지하며, `scripts/dev_session.sh`와 `scripts/dev_session.ps1`은 기존 문서/자동화와 호환하기 위한 wrapper입니다.

처음 한 번 설정합니다.

```bash
uv run terminalbridge setup
```

설정 과정에서 `ngrok`, 관리형 `cloudflare`, 일반 `external` 중 하나와 ChatGPT가 접근할 수 있는 `WORKSPACE_ROOT`, 기본 도움말 언어를 선택합니다. 각 사용자의 ngrok 또는 Cloudflare 설정을 사용하며 shell의 기존 값은 runtime `session.env`보다 우선합니다. 자세한 내용은 [공개 연결 모드](public-access.md)를 확인하세요.

프로젝트 명령어 도움말은 `uv run woojae help`로 확인할 수 있습니다. 한국어 도움말을 기본으로 보려면 setup 중 `Help language`를 `ko`로 저장하거나 `uv run woojae help --lang ko`를 사용하세요.

환경을 점검합니다.

```bash
uv run woojae doctor
```

전체 로컬 세션을 시작합니다.

```bash
uv run terminalbridge start
```

상태 확인:

```bash
uv run terminalbridge status
```

review UI 열기:

```bash
uv run terminalbridge open
```

종료:

```bash
uv run terminalbridge stop
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

`ngrok` 모드에서 `NGROK_HOST`는 선택 사항이며 없으면 temporary URL mode를 사용합니다. 관리형 `cloudflare`와 일반 `external` 모드에서는 `PUBLIC_MCP_URL`이 필수이며 Cloudflare는 사용자의 config path와 tunnel 이름도 필요합니다. `uv run terminalbridge copy-url`은 고정 공개 endpoint와 `MCP_ACCESS_TOKEN`이 모두 있을 때 동작합니다.

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
uv run woojae update
```

- `uv run woojae update`는 로컬에 커밋되지 않은 변경사항이 있으면 중단됩니다.
- 현재 branch를 `--ff-only`로 pull합니다.
- `uv sync`를 실행합니다.
- review와 MCP를 새 코드로 재시작하고, `PUBLIC_ACCESS_MODE=ngrok`일 때만 ngrok도 재시작합니다.
- 마지막 로컬 세션 상태를 출력합니다.
- MCP tool 변경이 포함된 업데이트 후에는 ChatGPT app connector를 refresh/reconnect하세요.

실제 변경 없이 업데이트 단계를 미리 보려면 다음 명령을 사용하세요.

```bash
uv run woojae update --dry-run
```

pull과 sync만 하고 자동 세션 재시작을 생략하려면 다음 명령을 사용하세요.

```bash
uv run woojae update --skip-restart
```

## 프로세스 제어

전체 연결 스택의 일반 운영에는 `terminalbridge`, 개별 Bridge 서비스 진단에는 `woojae`를 사용합니다.

```bash
uv run terminalbridge status
uv run woojae restart mcp
uv run woojae restart ngrok
uv run terminalbridge restart
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

저수준 `restart ngrok`과 `logs ngrok`은 ngrok 모드용입니다. Cloudflare와 일반 external 모드에서는 ngrok 시작·재시작이 차단됩니다. 선택된 전체 스택은 `uv run terminalbridge restart`, 관리형 Cloudflare 로그는 `uv run terminalbridge logs cloudflared`를 사용하고 일반 external connector는 별도로 관리하세요.

호환 wrapper는 계속 사용할 수 있습니다. 전체 스택 운영에는 `uv run terminalbridge ...`, 개별 서비스 진단에는 `uv run woojae ...`를 사용하세요.

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
uv run terminalbridge start
```

2. review UI를 엽니다.

```bash
uv run terminalbridge open
```

3. MCP URL을 clipboard에 복사하거나 URL 상태를 확인합니다.

```bash
uv run terminalbridge copy-url
```

`copy-url`은 실제 URL을 clipboard에 복사하지만 token을 터미널에 출력하지 않습니다. macOS는 `pbcopy`, Linux는 `xclip`, Windows는 `clip`이 있으면 사용합니다. `uv run terminalbridge mcp-url`은 redacted URL preview만 출력합니다.

MCP URL 형식:

ngrok 모드:

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

Cloudflare 또는 일반 external 모드 예시:

```text
https://terminalbridge.example.com/mcp?access_token=<TOKEN>
```

실제 token 값은 문서, screenshot, chat, GitHub issue에 붙여넣거나 공유하지 마세요.

4. ChatGPT에서 app/connector 생성 화면을 엽니다.

UI는 바뀔 수 있으므로 settings, connector, apps 영역에서 custom app 또는 custom MCP connector 생성을 선택합니다.

5. app creation form을 채웁니다.

- 아이콘: 선택 사항입니다.
- 이름: `Ouroboros Workspace Bridge` 또는 `Woojae Workspace Bridge`
- 설명: `Local MCP bridge for approved workspace file and command operations.`
- MCP 서버 URL: `uv run terminalbridge copy-url`로 복사한 URL을 붙여넣습니다.
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
uv run terminalbridge mcp-url
```

## Temporary ngrok URL 주의

`NGROK_HOST`가 없으면 `terminalbridge copy-url`이 안정적인 ngrok URL을 만들지 못할 수 있습니다. temporary ngrok URL은 재시작 후 바뀔 수 있어서 ChatGPT app의 MCP URL도 다시 수정해야 할 수 있습니다.

안정적으로 사용하려면 ngrok reserved domain을 만들고 `uv run terminalbridge setup`에서 `NGROK_HOST`를 설정하세요.

## Approval mode

- **Normal**: 기본값입니다. 모든 pending mutation에 사용자의 수동 승인 클릭이 필요합니다.
- **Safe Auto**: 조건에 맞는 low-risk command-only bundle만 자동 승인하고, 나머지는 manual review를 위해 pending으로 남깁니다.
- **YOLO**: 승인 단계 올패스 모드입니다. 모든 유효한 pending bundle을 수동 승인 클릭 없이 runner로 보냅니다. 실행 시점 검증과 실제 command failure는 그대로 적용됩니다.

처음에는 Normal을 사용하세요. Review 흐름을 충분히 이해한 뒤에만 Safe Auto를 사용하고, YOLO는 짧고 신뢰할 수 있는 개발 세션에서만 사용하세요.

다음 경우 ChatGPT 앱의 MCP 연결을 refresh하세요.

- `server.py` 변경
- MCP tool schema 변경
- `MCP_ACCESS_TOKEN` 변경
- public ngrok host 변경

권장 순서:

```bash
uv run terminalbridge restart
uv run terminalbridge status
```

그 다음 ChatGPT app의 MCP 연결을 refresh/reconnect합니다. Schema/annotation 변경이라면 live connector가 canonical 31개 default public tool을 노출하는지 확인합니다.

## 안전한 bundle 흐름

1. ChatGPT가 만든 bundle ID와 반환 status를 확인합니다.
2. Normal에서 `pending`이면 review UI에서 내용을 확인하고 작고 예상한 bundle만 승인합니다.
3. Safe Auto/YOLO에서 `running`으로 넘어갔다면 manual approval을 찾지 말고 terminal state를 wait/poll합니다.
4. 필요하면 `workspace_command_bundle_status`로 최종 result를 확인합니다.
5. 이전 bundle이 더 이상 `pending`/`running`이 아닐 때 다음 작업으로 넘어갑니다.

파일 수정, 테스트, 커밋이 한 bundle에 섞여 있으면 승인하지 마세요.

문제 해결은 [문제 해결](troubleshooting.md)을 참고하세요.
