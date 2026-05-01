# Ouroboros Workspace Bridge

<p align="center">
  <img src="assets/brand/ouroboros-by-KwakWooJae.png" alt="Ouroboros by KwakWooJae logo" width="220">
</p>

Part of Ouroboros by KwakWooJae.

Author: KwakWooJae

## 소개

Ouroboros Workspace Bridge는 ChatGPT가 사용자가 설정한 `WORKSPACE_ROOT` 안의 로컬 프로젝트를 안전하게 탐색, 수정, 검증하도록 돕는 개인용 local MCP server입니다. 위험한 파일 수정과 명령 실행은 pending bundle로 만들고, 로컬 review UI에서 사용자가 승인한 뒤 실행하는 구조를 기본으로 합니다.

## Overview

Ouroboros Workspace Bridge is a local MCP server for safely browsing, editing, and verifying projects under a configured `WORKSPACE_ROOT` from ChatGPT. Risky file changes and command execution are staged as pending bundles and run only after approval in the local review UI.

The recommended usage is from a repository checkout with `uv run woojae ...`. The old `scripts/dev_session.sh` and `scripts/dev_session.ps1` entrypoints are compatibility wrappers around the same CLI.

## Quick Start

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

During setup, choose the `WORKSPACE_ROOT` ChatGPT may access. Existing shell environment values such as `WORKSPACE_ROOT`, `NGROK_HOST`, and `MCP_ACCESS_TOKEN` are respected.

If `NGROK_HOST` is not configured, `uv run woojae start` uses ngrok temporary URL mode. `uv run woojae copy-url` requires both `NGROK_HOST` and `MCP_ACCESS_TOKEN`; it uses `pbcopy` on macOS, `xclip` on Linux, and `clip` on Windows when available. Use `uv run woojae mcp-url` to print a redacted URL preview.

Optional install helpers:

- `./install.sh` is Bash-only for macOS/Linux.
- `./install.ps1` is the Windows PowerShell equivalent.
- Both helpers install project dependencies and then point you back to the official `uv run woojae ...` commands.

Stop the local session:

```bash
uv run woojae stop
```

## Version and Updates

```bash
uv run woojae version
```

Run `uv run woojae version` to inspect your local version and git state. Version numbers are manually bumped for releases; they do not auto-bump on every push.

See [CHANGELOG.md](CHANGELOG.md) for user-facing changes and [docs/project/update-info.md](docs/project/update-info.md) for generated update metadata. Run `uv run python scripts/update_version_info.py` before release or documentation updates. CI checks the stable generated update-info sections; Recent Commits is a generated snapshot and can be refreshed with the same command.

## Runtime Data

Runtime data is stored outside the repository, usually under `~/.mcp_terminal_bridge/my-terminal-tool`.

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

`cleanup` is conservative and defaults to dry-run behavior unless `--apply` is passed. Session secrets, pending bundles, and process pid files are protected.

## Platform Support / 플랫폼 지원

- macOS: primary supported local workflow.
- Linux: supported for the Python supervisor workflow; desktop clipboard/notification conveniences may vary by distribution.
- Windows: supported through PowerShell for the Python supervisor workflow; ngrok, firewall, browser, and clipboard behavior may need local adjustment.

현재 공식 실행 명령은 모든 플랫폼에서 `uv run woojae ...`입니다. `scripts/dev_session.sh`와 `scripts/dev_session.ps1`은 기존 사용자를 위한 호환 wrapper입니다. `woojae copy-url`, 로컬 알림 같은 일부 편의 기능은 플랫폼별 도구에 의존할 수 있습니다.

## Documentation

Korean docs:

- [빠른 시작](docs/ko/quickstart.md)
- [로컬 세션 운영](docs/ko/local-session.md)
- [권장 로컬 작업 흐름](docs/ko/workflow.md)
- [문제 해결](docs/ko/troubleshooting.md)
- [ChatGPT 에이전트 지침](docs/ko/chatgpt-agent-usage.md)

English docs:

- [Quickstart](docs/en/quickstart.md)
- [Local session guide](docs/en/local-session.md)
- [Recommended local workflow](docs/en/workflow.md)
- [Troubleshooting](docs/en/troubleshooting.md)
- [ChatGPT agent instructions](docs/en/chatgpt-agent-usage.md)

Repository hygiene:

- [LICENSE](LICENSE)
- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## License

This project is licensed under the **KwakWooJae Non-Commercial License 1.0**.

Non-commercial use is permitted. Commercial use requires prior written permission from KwakWooJae.

For commercial permission, contact: kwakwoojae@gmail.com

This is a source-available project, not an OSI-approved open source project.

See [LICENSE](LICENSE).

## Repository Layout

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
├── server.py
└── uv.lock
```

Core implementation files:

- `server.py`: MCP tool registration and tool-facing orchestration.
- `scripts/command_bundle_review_server.py`: local HTTP review server routes and request handling.
- `terminal_bridge/mcp_runtime.py`: shared MCP runtime helpers for audit logging, tool-call journal wrapping, runtime directories, and command-bundle result conversion.
- `terminal_bridge/review_layout.py`: review UI shell, navigation, and shared CSS.
- `terminal_bridge/review_intents.py`: signed intent token import parsing helpers for the local review UI.

## Safety Notes

- Do not commit or paste real tokens, `.env` values, ngrok authtokens, or bearer tokens.
- Keep the review UI localhost-only.
- Treat the ngrok URL as externally reachable and token-protected.
- Approve only small, expected bundles.
- In the default public workflow, stage-and-wait proposal tools should keep action and command proposals to exactly one action or one command step.
- Reject bundles that mix unrelated edits, tests, commits, or surprising files.
