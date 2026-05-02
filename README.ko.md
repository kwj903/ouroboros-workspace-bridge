[English](README.md) | 한국어

# Ouroboros Workspace Bridge

<p align="center">
  <img src="assets/brand/ouroboros-by-KwakWooJae.png" alt="Ouroboros by KwakWooJae logo" width="220">
</p>

Ouroboros by KwakWooJae의 일부입니다.

작성자: KwakWooJae

Ouroboros Workspace Bridge는 ChatGPT가 사용자가 승인한 로컬 워크스페이스 안의 파일을 검사하고, 수정 proposal을 만들고, 검증 명령을 제안할 수 있게 해주는 로컬 MCP 브리지입니다. 위험할 수 있는 파일 변경이나 명령 실행은 바로 적용하지 않고, 로컬 review UI에 pending bundle로 올린 뒤 사용자가 승인해야 실행되도록 설계되어 있습니다.

영어 사용자는 [English README](README.md)를 보면 됩니다.

## 하는 일

- 설정된 `WORKSPACE_ROOT` 아래의 파일과 명령을 로컬 MCP 서버로 노출합니다.
- 위험한 수정과 명령을 직접 적용하지 않고 pending bundle로 생성합니다.
- 사용자가 각 pending bundle을 승인하거나 거절할 수 있는 로컬 review UI를 제공합니다.
- `uv run woojae ...` 기반으로 macOS, Linux, Windows 로컬 세션 워크플로우를 지원합니다.
- 런타임 설정, 로그, 백업, 승인 이력을 repository 밖에 저장합니다.

## 하지 않는 일

- 클라우드 서비스나 호스팅 SaaS가 아닙니다.
- 생성된 변경사항에 대한 사용자 검토를 대체하지 않습니다.
- 신뢰할 수 없는 워크스페이스나 공유 토큰에 연결해서는 안 됩니다.
- secret을 repository에 커밋할 필요가 없습니다.

## 안전 모델

```text
ChatGPT request
      ↓
Local MCP server
      ↓
Pending bundle
      ↓
Local review UI approval
      ↓
Apply file change or command
```

작고 예상 가능한 bundle만 승인하세요. 관련 없는 수정, 테스트, 커밋, 예상 밖의 파일 변경이 섞인 bundle은 거절하세요.

## 개요

권장 사용 방식은 repository checkout 상태에서 `uv run woojae ...` 명령을 실행하는 것입니다. 기존의 `scripts/dev_session.sh`와 `scripts/dev_session.ps1` entrypoint는 같은 CLI를 감싸는 호환 wrapper입니다.

## 빠른 시작

macOS/Linux:

```bash
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
uv run woojae start
uv run woojae copy-url
```

Windows PowerShell:

```powershell
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
uv run woojae start
uv run woojae mcp-url
```

setup 중에는 ChatGPT가 접근할 수 있는 `WORKSPACE_ROOT`와 기본 도움말 언어를 선택합니다. 기존 shell 환경값인 `WORKSPACE_ROOT`, `NGROK_HOST`, `MCP_ACCESS_TOKEN`, `WOOJAE_HELP_LANG`가 있으면 이를 존중합니다.

프로젝트 전용 명령 도움말은 다음으로 확인할 수 있습니다.

```bash
uv run woojae help
uv run woojae help --lang ko
```

setup 중 `Help language`를 `ko`로 설정하면 한국어 도움말을 기본값으로 사용할 수 있습니다.

`NGROK_HOST`가 설정되어 있지 않으면 `uv run woojae start`는 ngrok 임시 URL 모드를 사용합니다. `uv run woojae copy-url`은 `NGROK_HOST`와 `MCP_ACCESS_TOKEN`이 모두 필요하며, 사용 가능한 경우 macOS의 `pbcopy`, Linux의 `xclip`, Windows의 `clip`을 사용합니다. URL 미리보기는 다음 명령으로 확인할 수 있습니다.

```bash
uv run woojae mcp-url
```

선택 설치 helper:

- `./install.sh`: macOS/Linux용 Bash helper입니다.
- `./install.ps1`: Windows PowerShell용 helper입니다.
- 두 helper 모두 프로젝트 의존성을 설치한 뒤 공식 `uv run woojae ...` 명령으로 안내합니다.

로컬 세션 종료:

```bash
uv run woojae stop
```

## 버전과 업데이트

```bash
uv run woojae version
```

`uv run woojae version`으로 로컬 버전과 git 상태를 확인할 수 있습니다. 버전 번호는 release 시 수동으로 올리며, push할 때마다 자동으로 증가하지 않습니다.

사용자 관점 변경사항은 [CHANGELOG.md](CHANGELOG.md)를 확인하세요. 생성된 업데이트 메타데이터는 [docs/project/update-info.md](docs/project/update-info.md)에 있습니다. release나 문서 업데이트 전에는 다음 명령으로 업데이트 정보를 갱신할 수 있습니다.

```bash
uv run python scripts/update_version_info.py
```

CI는 안정적인 generated update-info section을 확인합니다. Recent Commits는 생성된 snapshot이며 같은 명령으로 갱신할 수 있습니다.

## 런타임 데이터

런타임 데이터는 보통 repository 밖의 `~/.mcp_terminal_bridge/my-terminal-tool` 아래에 저장됩니다.

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

`cleanup`은 보수적으로 동작하며, `--apply`를 넘기지 않으면 기본적으로 dry-run입니다. 세션 secret, pending bundle, process pid file은 보호됩니다.

## 플랫폼 지원

- macOS: 주 지원 로컬 워크플로우입니다.
- Linux: Python supervisor 워크플로우를 지원합니다. 데스크톱 클립보드/알림 편의 기능은 배포판마다 다를 수 있습니다.
- Windows: PowerShell을 통해 Python supervisor 워크플로우를 지원합니다. ngrok, firewall, browser, clipboard 동작은 로컬 환경에 따라 조정이 필요할 수 있습니다.

현재 공식 실행 명령은 모든 플랫폼에서 `uv run woojae ...`입니다. `scripts/dev_session.sh`와 `scripts/dev_session.ps1`은 기존 사용자를 위한 호환 wrapper입니다. `woojae copy-url`, 로컬 알림 같은 일부 편의 기능은 플랫폼별 도구에 의존할 수 있습니다.

## 문서

한국어 문서:

- [빠른 시작](docs/ko/quickstart.md)
- [로컬 세션 운영](docs/ko/local-session.md)
- [권장 로컬 작업 흐름](docs/ko/workflow.md)
- [문제 해결](docs/ko/troubleshooting.md)
- [ChatGPT 에이전트 지침](docs/ko/chatgpt-agent-usage.md)

영어 문서:

- [Quickstart](docs/en/quickstart.md)
- [Local session guide](docs/en/local-session.md)
- [Recommended local workflow](docs/en/workflow.md)
- [Troubleshooting](docs/en/troubleshooting.md)
- [ChatGPT agent instructions](docs/en/chatgpt-agent-usage.md)

Repository 관리:

- [LICENSE](LICENSE)
- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

Issue와 setup 도움:

- setup help, bug report, feature request는 GitHub issue template을 사용하세요.
- public issue에는 실제 token, ngrok authtoken, `.env` 값, 비공개 파일 내용을 포함하지 마세요.

## 라이선스

이 프로젝트는 **KwakWooJae Non-Commercial License 1.0**으로 배포됩니다.

비상업적 사용은 허용됩니다. 상업적 사용은 KwakWooJae의 사전 서면 허가가 필요합니다.

상업적 사용 문의: kwakwoojae@gmail.com

이 프로젝트는 source-available 프로젝트이며, OSI 승인 오픈소스 프로젝트가 아닙니다.

자세한 내용은 [LICENSE](LICENSE)를 확인하세요.

## Repository 구조

```text
my-terminal-tool/
├── assets/
├── docs/
│   ├── en/
│   ├── ko/
│   └── project/
├── scripts/
├── terminal_bridge/
├── tests/
├── pyproject.toml
├── README.md
├── README.ko.md
├── server.py
└── uv.lock
```

핵심 구현 파일:

- `server.py`: MCP tool 등록과 tool-facing orchestration.
- `scripts/command_bundle_review_server.py`: 로컬 HTTP review server route와 request handling.
- `terminal_bridge/mcp_runtime.py`: audit log, tool-call journal wrapping, runtime directory, command-bundle result conversion을 위한 공통 MCP runtime helper.
- `terminal_bridge/review_layout.py`: review UI shell, navigation, shared CSS.
- `terminal_bridge/review_intents.py`: 로컬 review UI의 signed intent token import parsing helper.

## 안전 주의사항

- 실제 token, `.env` 값, ngrok authtoken, bearer token을 커밋하거나 붙여넣지 마세요.
- review UI는 localhost 전용으로 유지하세요.
- ngrok URL은 외부에서 접근 가능한 token-protected URL로 취급하세요.
- 작고 예상 가능한 bundle만 승인하세요.
- 기본 public workflow에서는 stage-and-wait proposal tool이 action proposal과 command proposal을 각각 정확히 하나의 action 또는 하나의 command step으로 유지해야 합니다.
- 관련 없는 수정, 테스트, 커밋, 예상 밖의 파일 변경이 섞인 bundle은 거절하세요.
