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

The v0.1 recommended usage is from a repository checkout with `uv run woojae ...`.

## Quick Start

```bash
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
uv run woojae start
uv run woojae copy-url
```

During setup, choose the `WORKSPACE_ROOT` ChatGPT may access. Existing shell environment values such as `WORKSPACE_ROOT`, `NGROK_HOST`, and `MCP_ACCESS_TOKEN` are respected.

If `NGROK_HOST` is not configured, `uv run woojae start` uses ngrok temporary URL mode. `uv run woojae copy-url` requires both `NGROK_HOST` and `MCP_ACCESS_TOKEN`; it copies the real URL on macOS and prints only a redacted preview.

Stop the local session:

```bash
uv run woojae stop
```

## Platform Support / 플랫폼 지원

- macOS: supported and tested.
- Linux: experimental and not officially supported yet.
- Windows: not supported directly. WSL may work, but it is untested.

현재 Ouroboros Workspace Bridge는 macOS-first 로컬 개발 도구로 개발되고 있습니다. `woojae copy-url`, 로컬 알림 같은 일부 편의 기능은 macOS 전용 도구에 의존합니다.

## Documentation

Korean docs:

- [빠른 시작](docs/ko/quickstart.md)
- [로컬 세션 운영](docs/ko/local-session.md)
- [문제 해결](docs/ko/troubleshooting.md)
- [ChatGPT 에이전트 지침](docs/ko/chatgpt-agent-usage.md)

English docs:

- [Quickstart](docs/en/quickstart.md)
- [Local session guide](docs/en/local-session.md)
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

## Safety Notes

- Do not commit or paste real tokens, `.env` values, ngrok authtokens, or bearer tokens.
- Keep the review UI localhost-only.
- Treat the ngrok URL as externally reachable and token-protected.
- Approve only small, expected bundles.
- Reject bundles that mix unrelated edits, tests, commits, or surprising files.
