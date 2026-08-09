English | [한국어](README.ko.md)

# Ouroboros Workspace Bridge

<p align="center">
  <img src="assets/brand/ouroboros-by-KwakWooJae.png" alt="Ouroboros by KwakWooJae logo" width="220">
</p>

Local-first MCP bridge for safely letting ChatGPT work inside your workspace.

Ouroboros Workspace Bridge lets ChatGPT inspect a local project and propose file edits or commands without applying them directly. Mutating work is staged as a durable bundle and governed by the local approval policy: **Normal** requires a manual review click, while **Safe Auto** and **YOLO** can authorize eligible bundles without that click. The local runner still performs execution-time validation, backup/rollback handling, and terminal-state recording.

Part of Ouroboros by KwakWooJae.

Author: KwakWooJae

## Why use this?

- ChatGPT can inspect your local project under a configured `WORKSPACE_ROOT`.
- File edits are staged as reviewable proposals.
- Commands run only after the configured local approval policy authorizes the bundle; Normal is manual, while Safe Auto/YOLO may auto-authorize.
- Runtime data stays outside your repository.
- Built for `uv run terminalbridge ...` operation with `uv run woojae ...` available for low-level diagnostics.

## Quick Start

Prerequisites: Python 3.12+, `uv`, and a ChatGPT environment that can create a custom MCP app/connector. Each installation uses that user's own ngrok account, Cloudflare account/tunnel/domain, or another external HTTPS connector.

macOS/Linux:

```bash
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run terminalbridge setup
uv run terminalbridge start
uv run terminalbridge mcp-url
```

Windows PowerShell:

```powershell
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run terminalbridge setup
uv run terminalbridge start
uv run terminalbridge mcp-url
```

During setup, choose `ngrok`, managed `cloudflare`, or generic `external`, the `WORKSPACE_ROOT` ChatGPT may access, and the default help language. Existing shell and runtime settings are respected.

Public connection modes:

- `ngrok` (default): starts review, MCP, and the user's own ngrok connector.
- `cloudflare`: starts review, MCP, and the user's configured named Cloudflare Tunnel from their own account and config.
- `external`: starts review and MCP while another user-managed proxy or tunnel remains outside the project lifecycle.
- No maintainer token, domain, tunnel ID, or credential is a working product default.
- Keep the review UI local-only and run a shared-domain connector on only one computer at a time.

Optional browser onboarding:

```bash
uv run terminalbridge setup-ui
```

`setup-ui` opens a temporary localhost setup wizard for first-time users. It shows mode-aware ngrok, managed Cloudflare, or generic external guidance, workspace concepts, ChatGPT app connection, and the first success test. It does not replace `uv run terminalbridge setup` and does not start, stop, or restart the normal session.

`uv run terminalbridge mcp-url` prints a redacted URL preview for checking configuration without exposing the token. Use `uv run terminalbridge copy-url` when a fixed public endpoint, `MCP_ACCESS_TOKEN`, and a platform clipboard helper are configured and you are ready to paste the real token-protected MCP URL into ChatGPT.

Next steps:

- [Choose ngrok or your own public domain](docs/en/public-access.md)
- [Connect as a ChatGPT custom app](docs/en/chatgpt-app-setup.md)
- [Use the pending review UI](docs/en/pending-review-ui.md)

First success test:

```text
Use this workspace directory: /path/to/your/project
Show me a brief overview of this directory's structure and tell me what kind of project it looks like.
```

With the default Normal mode, approve only the expected pending bundle in the local review UI. If Safe Auto or YOLO is intentionally enabled, verify the bundle's `running`/terminal status instead of expecting a manual approval step.

Stop the local session:

```bash
uv run terminalbridge stop
```

Optional install helpers:

These scripts are optional OS-specific setup helpers. They do not replace `uv run terminalbridge setup`; they prepare local conveniences so the normal operator workflow is easier to use.

- `./install.sh`: Bash helper for macOS/Linux.
- `./install.ps1`: PowerShell helper for Windows.
- They install/sync Python dependencies and check or guide platform tools used by the local workflow.
- Platform tools include browser opening, clipboard copy helpers, and desktop notifications for pending review events when available.
- After running a helper, continue with `uv run terminalbridge setup` or `uv run terminalbridge setup-ui`.

## Update

From an existing checkout:

```bash
cd ouroboros-workspace-bridge
uv run woojae update
```

`woojae update` stops if local uncommitted changes are present. It pulls the current branch with `--ff-only`, runs `uv sync`, restarts the local session, and prints status.

Preview the update without changing files:

```bash
uv run woojae update --dry-run
```

After updates that change MCP tools, refresh or reconnect the ChatGPT app connector.

## After starting

- A local MCP server is running for the configured workspace.
- A localhost review UI is available.
- A token-protected MCP URL can be added to ChatGPT as a custom app/connector.
- Pending and completed bundles are reviewed at `http://127.0.0.1:8790/pending` and the history views.
- The default ChatGPT connector exposes a canonical **31-tool** MCP surface; `workspace_info` and smoke/schema checks use the same manifest.

## How it works

```text
ChatGPT
  -> Local MCP bridge
  -> Durable bundle
  -> Approval policy
       Normal: manual review
       Safe Auto / YOLO: policy-based auto authorization
  -> Atomic pending -> running claim
  -> Local runner
  -> applied / failed / interrupted
```

## Safety model

- ChatGPT does not directly edit files or run commands; it submits proposals to the Bridge runtime.
- Start with Normal mode and approve only small, expected bundles. If Safe Auto or YOLO is enabled, treat that mode itself as authorization for eligible pending bundles.
- Reject bundles that mix unrelated edits, tests, commits, or surprising files.
- Keep the review UI localhost-only.
- Treat every public MCP endpoint, whether ngrok or your own domain, as externally reachable and token-protected.

## Platform support

- macOS: supported through the shared Python supervisor workflow.
- Linux: supported through the shared Python supervisor workflow; desktop clipboard/notification conveniences may vary by distribution.
- Windows 10/11: supported through PowerShell and the shared Python supervisor workflow; ngrok or external-tunnel setup, firewall, browser, and clipboard behavior may need local adjustment.

CI runs the unit and smoke suites on GitHub-hosted Ubuntu, macOS, and Windows runners. Platform-specific desktop integrations still require local verification on the target machine.

Use `uv run terminalbridge ...` as the normal operator command for the complete connection stack on every platform. `uv run woojae ...` remains the lower-level diagnostic/update interface, and `scripts/dev_session.sh` / `scripts/dev_session.ps1` remain compatibility wrappers.

## Documentation

English docs:

- [Quickstart](docs/en/quickstart.md)
- [Public access modes](docs/en/public-access.md)
- [Connect as a ChatGPT custom app](docs/en/chatgpt-app-setup.md)
- [Use the pending review UI](docs/en/pending-review-ui.md)
- [Local session guide](docs/en/local-session.md)
- [Recommended local workflow](docs/en/workflow.md)
- [Troubleshooting](docs/en/troubleshooting.md)
- [ChatGPT agent instructions](docs/en/chatgpt-agent-usage.md)

Korean docs:

- [빠른 시작](docs/ko/quickstart.md)
- [공개 연결 모드](docs/ko/public-access.md)
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

- `server.py`: MCP registration, public wrapper signatures, annotations, validation, and thin adapters.
- `terminal_bridge/public_tools.py`: canonical default 31-tool public MCP manifest and annotation policy helpers.
- `terminal_bridge/bundles.py`: canonical filesystem bundle store for atomic JSON persistence, request identity/indexing, generation signaling, claim, transition, and finalization.
- `terminal_bridge/bundle_service.py`: focused stage/find/status/list/cancel orchestration over the canonical bundle store.
- `terminal_bridge/mcp_tools/`: helper modules for read-only inspection, proposal construction, async wait/status flows, and runtime status views.
- `scripts/command_bundle_review_server.py`: local HTTP review server routes, bundle views, approval-mode handling, and long-poll state updates.
- `scripts/command_bundle_runner.py`: validated single-workspace-cwd execution, snapshots/backups, rollback, and terminal bundle finalization.
- `terminal_bridge/mcp_runtime.py`: shared MCP runtime helpers for audit logging, async-aware tool-call journaling, and runtime directory setup.
- `terminal_bridge/operator_cli.py`: `terminalbridge` complete-stack operator CLI; `terminal_bridge/cli.py` keeps lower-level `woojae` diagnostics/update commands, with shared primitives in `terminal_bridge/cli_common.py`.
- `terminal_bridge/review_layout.py`: review UI shell, navigation, and shared CSS.
- `terminal_bridge/review_intents.py`: signed intent token import parsing helpers for the local review UI.

## Safety notes

- Do not commit or paste real tokens, `.env` values, ngrok authtokens, or bearer tokens.
- Approve only small, expected bundles.
- In the default public workflow, stage-and-wait proposal tools should keep action and command proposals to exactly one action or one command step.
- Reject bundles that mix unrelated edits, tests, commits, or surprising files.
- Do not include real tokens, private file contents, or workspace secrets in public issues.
