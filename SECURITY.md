# Security Policy

Ouroboros Workspace Bridge, part of Ouroboros by KwakWooJae, is a local MCP server. It can access files under the configured `WORKSPACE_ROOT` and can run approved local command/action/patch bundles after review.

## Secret Handling

Keep these values private:

- `MCP_ACCESS_TOKEN`
- ngrok authtokens
- access tokens
- bearer tokens
- `.env` values
- shell secret values

Do not paste real tokens into README files, GitHub issues, logs, screenshots, test fixtures, or ChatGPT messages.

## Local Review UI

The review UI should remain localhost-only. It is intended for local approval of pending bundles, not for public internet exposure.

The ngrok URL is externally reachable. Token protection is required whenever the MCP server is exposed through ngrok.

Approve only expected small bundles. Reject bundles that:

- mix unrelated edits, tests, and commits
- touch unexpected files
- include surprising commands
- are too large to review confidently

## Secret Rotation

If a token may have been exposed:

1. Stop the local session.
2. Regenerate the token through `woojae setup`, `scripts/dev_session.sh configure`, or your shell secret manager.
3. Restart the local session.
4. Refresh the ChatGPT MCP connection.

Do not commit old or new token values while rotating secrets.

## Reporting Vulnerabilities

Open a private report or contact the maintainer. Do not disclose exploitable details publicly before a fix is available.
