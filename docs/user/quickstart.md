# Quickstart

This is the short first-run path for Workspace Terminal Bridge.

## Prerequisites

- macOS is recommended for now.
- Python 3.12+
- `uv`
- ngrok account and ngrok CLI

## Prepare ngrok

1. Sign up for ngrok.
2. Install the ngrok CLI.
3. Configure your ngrok authtoken with the ngrok CLI.
4. A reserved ngrok domain is optional. Temporary URL mode works for a first run, but `woojae copy-url` requires a configured `NGROK_HOST`.

Do not put ngrok auth tokens, MCP access tokens, or other secrets in repository files.

## First Setup

From a repository checkout:

```bash
uv sync
uv run woojae setup
```

During setup:

- choose the `WORKSPACE_ROOT` that ChatGPT is allowed to access
- keep any existing shell environment values when they are already set
- save private runtime settings outside the repository

Existing shell values such as `WORKSPACE_ROOT`, `NGROK_HOST`, and `MCP_ACCESS_TOKEN` take precedence over runtime `session.env`.

## Start

```bash
uv run woojae start
```

The review UI opens at:

```text
http://127.0.0.1:8790/pending
```

## Connect ChatGPT

Show a redacted MCP URL preview:

```bash
uv run woojae mcp-url
```

Copy the real MCP URL to the macOS clipboard:

```bash
uv run woojae copy-url
```

`woojae mcp-url` prints only a redacted preview. `woojae copy-url` does not print the real token. If `NGROK_HOST` is not configured, start the session and check ngrok output or logs for the temporary URL.

## Approve Bundles

Use the review UI to inspect pending bundles before they run. Approve only small, expected bundles. Reject anything that is too large, unrelated to the request, or surprising.

Useful pages:

```text
http://127.0.0.1:8790/pending
http://127.0.0.1:8790/history
http://127.0.0.1:8790/servers
```

## Stop

```bash
uv run woojae stop
```
