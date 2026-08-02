# Security Policy

Ouroboros Workspace Bridge, part of Ouroboros by KwakWooJae, is a local MCP server. It can access files under the configured `WORKSPACE_ROOT` and can run approved local command/action/patch bundles after review.

## Secret Handling

Keep these values private:

- `MCP_ACCESS_TOKEN`
- ngrok authtokens
- Cloudflare or other external tunnel credentials
- access tokens
- bearer tokens
- `.env` values
- shell secret values

Do not paste real tokens into README files, GitHub issues, logs, screenshots, test fixtures, or ChatGPT messages.

## Local Review UI

The review UI should remain localhost-only. It is intended for local approval of pending bundles, not for public internet exposure.

Every public MCP endpoint is externally reachable, whether it uses ngrok or a user-managed domain. Token protection is always required. `PUBLIC_MCP_URL` must not contain an access token, embedded credentials, query string, or fragment.

External tunnels must route only to the local MCP service at `127.0.0.1:8787`. Never route the review UI at `127.0.0.1:8790`. A shared external-domain connector should run on only one computer at a time so related tool calls cannot be distributed across different local workspaces.

Approve only expected small bundles. Reject bundles that:

- mix unrelated edits, tests, and commits
- touch unexpected files
- include surprising commands
- are too large to review confidently

## Secret Rotation

If a token may have been exposed:

1. Stop the local session.
2. Regenerate the token through `uv run woojae setup` or your shell secret manager.
3. Restart the local session.
4. Refresh the ChatGPT MCP connection.

Do not commit old or new token values while rotating secrets.

## Reporting Vulnerabilities

Open a private report or contact the maintainer. Do not disclose exploitable details publicly before a fix is available.
