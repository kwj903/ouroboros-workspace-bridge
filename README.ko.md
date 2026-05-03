[English](README.md) | 한국어

# Ouroboros Workspace Bridge

<p align="center">
  <img src="assets/brand/ouroboros-by-KwakWooJae.png" alt="Ouroboros by KwakWooJae logo" width="220">
</p>

ChatGPT가 내 로컬 프로젝트를 바로 수정하지 않고, 변경 proposal을 만든 뒤 내가 localhost review UI에서 승인해야만 적용되게 해주는 로컬 MCP 브리지입니다.

Ouroboros Workspace Bridge는 ChatGPT가 설정된 로컬 workspace를 살펴보고 파일 수정이나 명령 실행을 제안할 수 있게 해줍니다. 위험할 수 있는 작업은 바로 실행되지 않고 pending bundle로 올라오며, 사용자가 로컬 review UI에서 승인한 뒤에만 적용됩니다.

Ouroboros by KwakWooJae의 일부입니다.

작성자: KwakWooJae

## 왜 쓰나요?

- ChatGPT가 설정된 `WORKSPACE_ROOT` 안의 로컬 프로젝트를 살펴볼 수 있습니다.
- 파일 수정은 바로 적용되지 않고 검토 가능한 proposal로 만들어집니다.
- 명령은 사용자가 로컬에서 승인한 뒤에만 실행됩니다.
- 런타임 데이터는 repository 밖에 저장됩니다.
- 공식 실행 흐름은 `uv run woojae ...`입니다.

## 빠른 시작

준비물: Python 3.12+, `uv`, ngrok CLI, custom MCP app/connector를 만들 수 있는 ChatGPT 환경.

macOS/Linux:

```bash
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
uv run woojae start
uv run woojae mcp-url
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

선택형 브라우저 온보딩:

```bash
uv run woojae setup-ui
```

`setup-ui`는 처음 쓰는 사용자를 위한 임시 localhost 설정 마법사입니다. ngrok 준비, workspace 개념, ChatGPT 앱 연결, 첫 성공 테스트를 한 화면에서 안내합니다. `uv run woojae setup`을 대체하지 않으며, 일반 review/MCP 세션을 시작하거나 중지하거나 재시작하지 않습니다.

`uv run woojae mcp-url`은 token을 노출하지 않고 redacted URL preview만 보여줍니다. `NGROK_HOST`, `MCP_ACCESS_TOKEN`, 플랫폼 clipboard helper가 준비되어 있고 실제 연결용 URL을 ChatGPT에 붙여넣을 준비가 되었을 때 `uv run woojae copy-url`을 사용하세요.

다음 단계:

- [ChatGPT 앱으로 연결하기](docs/ko/chatgpt-app-setup.md)
- [pending review UI 사용하기](docs/ko/pending-review-ui.md)

첫 성공 테스트:

```text
작업할 디렉토리는 /path/to/your/project 입니다.
이 디렉토리의 구성을 간단히 보여주고, 어떤 종류의 프로젝트인지 요약해줘.
```

로컬 review UI에서 예상한 pending bundle인지 확인한 뒤 승인하세요.

로컬 세션 종료:

```bash
uv run woojae stop
```

선택 설치 helper:

이 스크립트는 필수가 아닌 OS별 설치 보조 도구입니다. `uv run woojae setup`을 대체하지 않고, 일반적인 `uv run woojae ...` 흐름을 더 편하게 사용할 수 있도록 로컬 편의 기능을 준비합니다.

- `./install.sh`: macOS/Linux용 Bash helper.
- `./install.ps1`: Windows PowerShell용 helper.
- Python 의존성을 설치/동기화하고, 로컬 워크플로우에 필요한 플랫폼 도구를 확인하거나 안내합니다.
- 플랫폼 도구에는 브라우저 열기, clipboard 복사 helper, pending review 알림용 desktop notification 기능이 포함됩니다.
- helper 실행 후에는 `uv run woojae setup` 또는 `uv run woojae setup-ui`로 실제 설정을 이어가세요.

## 업데이트

기존 설치 디렉토리에서 실행하세요.

```bash
cd ouroboros-workspace-bridge
uv run woojae update
```

`woojae update`는 로컬에 커밋되지 않은 변경사항이 있으면 중단됩니다. 현재 branch를 `--ff-only`로 pull하고, `uv sync`를 실행하고, 로컬 세션을 재시작한 뒤 상태를 출력합니다.

실제 변경 없이 업데이트 단계를 미리 보려면 다음 명령을 사용하세요.

```bash
uv run woojae update --dry-run
```

MCP tool이 바뀐 업데이트 후에는 ChatGPT app connector를 refresh/reconnect하세요.

## 실행 후 확인할 것

- 설정한 workspace를 대상으로 local MCP server가 실행됩니다.
- localhost review UI가 열릴 준비가 됩니다.
- ChatGPT custom app/connector에 넣을 token-protected MCP URL을 만들 수 있습니다.
- Pending bundle은 `http://127.0.0.1:8790/pending`에서 검토합니다.

## 동작 방식

```text
ChatGPT
  -> Local MCP bridge
  -> Pending bundle
  -> Local review UI approval
  -> File change or command
```

## 안전 모델

- ChatGPT는 파일을 직접 수정하거나 명령을 직접 실행하지 않습니다.
- 작고 예상 가능한 bundle만 승인하세요.
- 관련 없는 수정, 테스트, 커밋, 예상 밖의 파일이 섞인 bundle은 거절하세요.
- review UI는 localhost 전용으로 유지하세요.
- ngrok URL은 외부에서 접근 가능한 token-protected URL로 취급하세요.

## 플랫폼 지원

- macOS: 주 지원 로컬 워크플로우입니다.
- Linux: Python supervisor 워크플로우를 지원합니다. 데스크톱 clipboard/notification 편의 기능은 배포판마다 다를 수 있습니다.
- Windows: PowerShell을 통해 Python supervisor 워크플로우를 지원합니다. ngrok, firewall, browser, clipboard 동작은 로컬 환경에 따라 조정이 필요할 수 있습니다.

모든 플랫폼에서 공식 명령은 `uv run woojae ...`입니다. `scripts/dev_session.sh`와 `scripts/dev_session.ps1`은 기존 사용자를 위한 호환 wrapper입니다.

## 문서

한국어 문서:

- [빠른 시작](docs/ko/quickstart.md)
- [ChatGPT 앱으로 연결하기](docs/ko/chatgpt-app-setup.md)
- [pending review UI 사용하기](docs/ko/pending-review-ui.md)
- [로컬 세션 운영](docs/ko/local-session.md)
- [권장 로컬 작업 흐름](docs/ko/workflow.md)
- [문제 해결](docs/ko/troubleshooting.md)
- [ChatGPT 에이전트 지침](docs/ko/chatgpt-agent-usage.md)

영어 문서:

- [Quickstart](docs/en/quickstart.md)
- [Connect as a ChatGPT custom app](docs/en/chatgpt-app-setup.md)
- [Use the pending review UI](docs/en/pending-review-ui.md)
- [Local session guide](docs/en/local-session.md)
- [Recommended local workflow](docs/en/workflow.md)
- [Troubleshooting](docs/en/troubleshooting.md)
- [ChatGPT agent instructions](docs/en/chatgpt-agent-usage.md)

Repository 관리:

- [LICENSE](LICENSE)
- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## 런타임 데이터

런타임 데이터는 보통 repository 밖의 `~/.mcp_terminal_bridge/my-terminal-tool` 아래에 저장됩니다.

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

`cleanup`은 보수적으로 동작하며, `--apply`를 넘기지 않으면 기본적으로 dry-run입니다. 세션 secret, pending bundle, process pid file은 보호됩니다.

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
- 작고 예상 가능한 bundle만 승인하세요.
- 기본 public workflow에서는 stage-and-wait proposal tool이 action proposal과 command proposal을 각각 정확히 하나의 action 또는 하나의 command step으로 유지해야 합니다.
- 관련 없는 수정, 테스트, 커밋, 예상 밖의 파일 변경이 섞인 bundle은 거절하세요.
- public issue에는 실제 token, 비공개 파일 내용, workspace secret을 포함하지 마세요.
