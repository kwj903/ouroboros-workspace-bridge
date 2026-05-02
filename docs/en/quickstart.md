# Quickstart

This is the short first-run path for Ouroboros Workspace Bridge.

The official command form is `uv run woojae ...`. `scripts/dev_session.sh` and `scripts/dev_session.ps1` are compatibility wrappers for older workflows.

## Prerequisites

- macOS: primary supported local workflow.
- Linux: supported for the Python supervisor workflow. Clipboard and notification behavior may vary by distribution.
- Windows: supported through PowerShell for the Python supervisor workflow. ngrok, firewall, browser, and clipboard behavior may need local adjustment.
- Python 3.12+
- `uv`
- ngrok account and ngrok CLI

## Prepare ngrok

1. Sign up for ngrok.
2. Install the ngrok CLI.
3. Configure your ngrok authtoken with the ngrok CLI.
4. A reserved ngrok domain is optional. Temporary URL mode works for a first run, but `woojae copy-url` requires a configured `NGROK_HOST`.

Do not put ngrok auth tokens, MCP access tokens, or other secrets in repository files.

## First Setup: macOS/Linux

From a repository checkout:

```bash
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
```

You can optionally use the Bash helper:

```bash
./install.sh
uv run woojae setup
```

`install.sh` is Bash-only. On Windows PowerShell, use `install.ps1`.

## First Setup: Windows PowerShell

From a repository checkout:

```powershell
git clone https://github.com/kwj903/ouroboros-workspace-bridge.git
cd ouroboros-workspace-bridge
uv sync
uv run woojae setup
```

You can optionally use the PowerShell helper:

```powershell
.\install.ps1
uv run woojae setup
```

During setup:

- choose the `WORKSPACE_ROOT` that ChatGPT is allowed to access
- choose the default help language with `Help language [auto/en/ko]`
- keep any existing shell environment values when they are already set
- save private runtime settings outside the repository

Existing shell values such as `WORKSPACE_ROOT`, `NGROK_HOST`, `MCP_ACCESS_TOKEN`, and `WOOJAE_HELP_LANG` take precedence over runtime `session.env`.

Project-specific command help is available with `uv run woojae help`. Use `uv run woojae help --lang ko` for Korean help, or save `Help language` as `ko` during setup.

## Start

```bash
uv run woojae start
```

The review UI opens at:

```text
http://127.0.0.1:8790/pending
```

## Connect ChatGPT

If you are unsure what to enter in each field of the new app screen, see [Connect as a ChatGPT custom app](chatgpt-app-setup.md) as well. After connecting, see [Use the pending review UI](pending-review-ui.md) for the approval screen.

1. Start the local session.

```bash
uv run woojae start
```

2. Open the local review UI.

```bash
uv run woojae open
```

3. Copy the MCP URL.

```bash
uv run woojae copy-url
```

`copy-url` copies the real MCP URL to the clipboard. It uses `pbcopy` on macOS, `xclip` on Linux, and `clip` on Windows when available. `uv run woojae mcp-url` prints only a redacted URL preview. It does not print the token. The URL format is:

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

Do not paste or share the real token in docs, screenshots, chats, or GitHub issues.

4. In ChatGPT, open the app/connector creation UI.

The UI may change, so use the settings, connector, or apps area that allows creating a custom app or custom MCP connector.

5. Fill the app creation form.

- Icon: optional.
- Name: `Ouroboros Workspace Bridge` or `Woojae Workspace Bridge`
- Description: `Local MCP bridge for approved workspace file and command operations.`
- MCP server URL: paste the URL copied by `uv run woojae copy-url`.
- Authentication: choose `No auth` or equivalent if the access token is already included in the MCP URL query string.
- Advanced OAuth settings: leave empty unless the product UI requires otherwise.
- Security warning checkbox: custom MCP servers can access data and tools. Enable it only for your own trusted local bridge after understanding the risk.

If the UI forces OAuth, this bridge may not use that mode. Choose the mode that allows a direct MCP URL without OAuth.

After creating the app, refresh or reconnect the connector. Confirm tools are visible and that the local review page is open:

```text
http://127.0.0.1:8790/pending
```

For a first test, ask ChatGPT:

```text
Use this workspace directory: /path/to/your/project
Show me a brief overview of this directory's structure and tell me what kind of project it looks like.
```

When the expected pending bundle appears, read it in the local review UI and approve it. This confirms that ChatGPT, the MCP bridge, and the review UI are connected end to end.

To print only a redacted URL preview:

```bash
uv run woojae mcp-url
```

## Approval Mode

- Normal: default, manual approval.
- Safe Auto: low-risk command-only bundles may be auto-approved. Normal or Safe Auto is recommended for regular users.
- YOLO: for trusted short sessions only. Do not leave it on.

## Temporary ngrok URL Caveat

If `NGROK_HOST` is not configured, `woojae copy-url` may not work. A temporary ngrok URL can change after restart, so the ChatGPT app MCP URL may need to be updated.

For stable usage, create a reserved ngrok domain and set `NGROK_HOST` during `uv run woojae setup`.

## Update Existing Installation

```bash
cd ouroboros-workspace-bridge
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

- `git pull` updates local files.
- `uv sync` refreshes dependencies if `pyproject.toml` or the lock file changed.
- `uv run woojae restart-session` restarts review, MCP, and ngrok with the new code.
- `uv run woojae status` should show review and mcp reachable.
- After MCP tool changes, refresh or reconnect the ChatGPT app connector.

## Approve Bundles

Use the review UI to inspect pending bundles before they run. Approve only small, expected bundles. Reject anything that is too large, unrelated to the request, or surprising.

Useful pages:

```text
http://127.0.0.1:8790/pending
http://127.0.0.1:8790/history
http://127.0.0.1:8790/servers
```

## License

This project is licensed under the **KwakWooJae Non-Commercial License 1.0**. Non-commercial use is permitted. Commercial use requires prior written permission from KwakWooJae.

Commercial permission contact: kwakwoojae@gmail.com

See [LICENSE](../../LICENSE).

## Stop

```bash
uv run woojae stop
```
