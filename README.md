English | [한국어](README.ko.md)

# Ouroboros Workspace Bridge

<p align="center">
  <img src="assets/brand/ouroboros-by-KwakWooJae.png" alt="Ouroboros by KwakWooJae logo" width="220">
</p>

Local-first MCP bridge for safely letting ChatGPT work inside your workspace.

Ouroboros Workspace Bridge lets ChatGPT inspect a local project and propose file edits or commands without applying them directly. Risky work is staged as a pending bundle, shown in a localhost review UI, and applied only after you approve it.

Part of Ouroboros by KwakWooJae.

Author: KwakWooJae

## Why use this?

- ChatGPT can inspect your local project under a configured `WORKSPACE_ROOT`.
- File edits are staged as reviewable proposals.
- Commands run only after local approval.
- Runtime data stays outside your repository.
- Built for `uv run woojae ...` workflows.

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

`uv run woojae copy-url` copies the real token-protected MCP URL when `NGROK_HOST`, `MCP_ACCESS_TOKEN`, and a platform clipboard helper are available. `uv run woojae mcp-url` prints a redacted URL preview for checking configuration without exposing the token.

Next steps:

- [Connect as a ChatGPT custom app](docs/en/chatgpt-app-setup.md)
- [Use the pending review UI](docs/en/pending-review-ui.md)

First success test:

```text
Use this workspace directory: /path/to/your/project
Show me a brief overview of this directory's structure and tell me what kind of project it looks like.
```

Approve only the expected pending bundle in the local review UI.

Stop the local session:

```bash
uv run woojae stop
```

Optional install helpers:

- `./install.sh`: Bash helper for macOS/Linux.
- `./install.ps1`: PowerShell helper for Windows.
- Both helpers install dependencies and point you back to `uv run woojae ...`.

## After starting

- A local MCP server is running for the configured workspace.
- A localhost review UI is available.
- A token-protected MCP URL can be added to ChatGPT as a custom app/connector.
- Pending bundles are reviewed at `http://127.0.0.1:8790/pending`.

## How it works

```text
ChatGPT
  -> Local MCP bridge
  -> Pending bundle
  -> Local review UI approval
  -> File change or command
```

## Safety model

- ChatGPT does not directly edit files or run commands.
- Approve only small, expected bundles.
- Reject bundles that mix unrelated edits, tests, commits, or surprising files.
- Keep the review UI localhost-only.
- Treat the ngrok URL as externally reachable and token-protected.

## Platform support

- macOS: primary supported local workflow.
- Linux: supported for the Python supervisor workflow; desktop clipboard/notification conveniences may vary by distribution.
- Windows: supported through PowerShell for the Python supervisor workflow; ngrok, firewall, browser, and clipboard behavior may need local adjustment.

The official command form on every platform is `uv run woojae ...`. `scripts/dev_session.sh` and `scripts/dev_session.ps1` remain compatibility wrappers.

## Documentation

English docs:

- [Quickstart](docs/en/quickstart.md)
- [Connect as a ChatGPT custom app](docs/en/chatgpt-app-setup.md)
- [Use the pending review UI](docs/en/pending-review-ui.md)
- [Local session guide](docs/en/local-session.md)
- [Recommended local workflow](docs/en/workflow.md)
- [Troubleshooting](docs/en/troubleshooting.md)
- [ChatGPT agent instructions](docs/en/chatgpt-agent-usage.md)

Korean docs:

- [빠른 시작](docs/ko/quickstart.md)
- [ChatGPT 앱으로 연결하기](docs/ko/chatgpt-app-setup.md)
- [pending review UI 사용하기](docs/ko/pending-review-ui.md)
- [로컬 세션 운영](docs/ko/local-session.md)
- [권장 로컬 작업 흐름](docs/ko/workflow.md)
- [문제 해결](docs/ko/troubleshooting.md)
- [ChatGPT 에이전트 지침](docs/ko/chatgpt-agent-usage.md)

Repository hygiene:

- [LICENSE](LICENSE)
- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Runtime data

Runtime data is stored outside the repository, usually under `~/.mcp_terminal_bridge/my-terminal-tool`.

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

`cleanup` is conservative and defaults to dry-run behavior unless `--apply` is passed. Session secrets, pending bundles, and process pid files are protected.

## License

This project is licensed under the **KwakWooJae Non-Commercial License 1.0**.

Non-commercial use is permitted. Commercial use requires prior written permission from KwakWooJae.

For commercial permission, contact: kwakwoojae@gmail.com

This is a source-available project, not an OSI-approved open source project.

See [LICENSE](LICENSE).

## Repository layout

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

Core implementation files:

- `server.py`: MCP tool registration and tool-facing orchestration.
- `scripts/command_bundle_review_server.py`: local HTTP review server routes and request handling.
- `terminal_bridge/mcp_runtime.py`: shared MCP runtime helpers for audit logging, tool-call journal wrapping, runtime directories, and command-bundle result conversion.
- `terminal_bridge/review_layout.py`: review UI shell, navigation, and shared CSS.
- `terminal_bridge/review_intents.py`: signed intent token import parsing helpers for the local review UI.

## Safety notes

- Do not commit or paste real tokens, `.env` values, ngrok authtokens, or bearer tokens.
- Approve only small, expected bundles.
- In the default public workflow, stage-and-wait proposal tools should keep action and command proposals to exactly one action or one command step.
- Reject bundles that mix unrelated edits, tests, commits, or surprising files.
- Do not include real tokens, private file contents, or workspace secrets in public issues.
