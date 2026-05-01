# Ouroboros Workspace Bridge

<p align="center">
  <img src="assets/brand/ouroboros-by-KwakWooJae.png" alt="Ouroboros by KwakWooJae logo" width="220">
</p>

Part of Ouroboros by KwakWooJae.

Author: KwakWooJae

Ouroboros Workspace Bridge is a local MCP bridge that lets ChatGPT inspect, edit, and verify files inside a user-approved workspace. It is designed for local-first development workflows where every risky file change or command is staged for review before it runs.

한국어 사용자는 [빠른 시작](docs/ko/quickstart.md)과 [로컬 세션 운영](docs/ko/local-session.md)을 먼저 보면 됩니다.

## What it does

- Exposes a local MCP server for files and commands under a configured `WORKSPACE_ROOT`.
- Stages risky edits and commands as pending bundles instead of applying them directly.
- Provides a local review UI where the user approves or rejects each pending bundle.
- Supports macOS, Linux, and Windows local session workflows through `uv run woojae ...`.
- Stores runtime settings, logs, backups, and approval history outside the repository.

## What it does not do

- It is not a cloud service or hosted SaaS.
- It does not remove the need to review generated changes.
- It should not be connected to untrusted workspaces or shared tokens.
- It does not require committing secrets into the repository.

## Safety model

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

Approve only small, expected bundles. Reject bundles that mix unrelated edits, tests, commits, or surprising files.

## Overview

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

During setup, choose the `WORKSPACE_ROOT` ChatGPT may access and the default help language. Existing shell environment values such as `WORKSPACE_ROOT`, `NGROK_HOST`, `MCP_ACCESS_TOKEN`, and `WOOJAE_HELP_LANG` are respected.

Project-specific command help is available with `uv run woojae help`. Use `uv run woojae help --lang ko` or set `Help language` to `ko` during setup for Korean help by default.

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

Issues and setup help:

- Use the GitHub issue templates for setup help, bug reports, and feature requests.
- Do not include real tokens, ngrok authtokens, `.env` values, or private file contents in public issues.

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
