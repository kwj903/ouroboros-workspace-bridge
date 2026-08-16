# Public access modes

Ouroboros Workspace Bridge has one shared MCP and review core with three operator modes. The recommended command is:

```bash
uv run terminalbridge setup
uv run terminalbridge start
uv run terminalbridge status
```

`uv run woojae ...` remains available as the low-level Bridge supervisor for debugging and compatibility.

For an OS service manager, run the full stack as one foreground lifecycle instead of periodically re-running `start`:

```bash
uv run terminalbridge supervise
```

`supervise` stays alive, reuses healthy review/MCP/tunnel children, reaps exited children, and restarts only missing managed processes. A service manager such as macOS launchd should own this foreground process with its native restart policy (`RunAtLoad` + `KeepAlive` on launchd); a `StartInterval` polling job is not needed. `terminalbridge stop` explicitly pauses managed children while the supervisor remains alive, and `terminalbridge start` resumes normal supervision.

## Ownership rule

Every installation uses infrastructure owned by that user:

- the user's own `MCP_ACCESS_TOKEN`;
- the user's own ngrok account and domain; or
- the user's own Cloudflare account, domain, tunnel, config, and credentials.

The repository does not ship a maintainer token, tunnel credential, tunnel ID, public domain, or user-specific absolute path as a working default. Example domains in the documentation are placeholders.

## ngrok mode

ngrok remains the backward-compatible default.

```text
PUBLIC_ACCESS_MODE=ngrok
NGROK_HOST=<optional-fixed-ngrok-domain>
```

Start explicitly or use the saved mode:

```bash
uv run terminalbridge start --mode ngrok
# or
uv run terminalbridge start
```

The operator starts and manages:

- the localhost review UI;
- the local MCP server;
- the user's ngrok connector.

If `NGROK_HOST` is empty, ngrok may use a temporary URL. A fixed ngrok host is required for a stable ChatGPT connector URL.

## Managed Cloudflare mode

Choose Cloudflare when the user has created a named Cloudflare Tunnel and a public hostname in their own Cloudflare account.

The compatibility settings remain external at the Bridge layer, while the operator provider selects managed Cloudflare lifecycle:

```text
PUBLIC_ACCESS_MODE=external
EXTERNAL_TUNNEL_PROVIDER=cloudflare
PUBLIC_MCP_URL=https://terminalbridge.example.com/mcp
CLOUDFLARED_CONFIG_PATH=~/.cloudflared/terminalbridge.yml
CLOUDFLARED_TUNNEL_NAME=my-terminalbridge
CLOUDFLARED_BIN=cloudflared
```

Start explicitly or use the saved mode:

```bash
uv run terminalbridge start --mode cloudflare
# or
uv run terminalbridge start
```

The operator starts and manages:

- the localhost review UI;
- the local MCP server;
- the user's configured `cloudflared` connector.

The Cloudflare config must route the user's public hostname only to:

```text
http://127.0.0.1:8787
```

Never publish the review UI:

```text
http://127.0.0.1:8790/pending
```

Cloudflare account login, tunnel creation, DNS routing, credential storage, and config ownership remain the user's responsibility. The project only starts and stops the configured connector.

### Optional Cloudflare Access Managed OAuth

OAuth-capable MCP clients can use Cloudflare Access Managed OAuth instead of placing the existing `MCP_ACCESS_TOKEN` in their connector URL. This is an **additional authentication path**, not a replacement for static-token authentication, so an existing ChatGPT connector and an OAuth client can share the same local MCP server.

Configure both values to enable Access JWT verification at the origin:

```text
CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
CLOUDFLARE_ACCESS_AUDIENCE=<access-application-aud>
```

Configuring only one value fails closed. Leaving both unset preserves the existing `MCP_ACCESS_TOKEN` behavior only.

For Managed OAuth, protect the MCP hostname/path with a Cloudflare Access self-hosted application and store that application's exact AUD and team domain in the private Bridge runtime settings. Before a request reaches FastMCP, the origin validates the `Cf-Access-Jwt-Assertion` provided after Access authentication, including:

- RS256 and `kid`;
- the rotating Cloudflare team JWKS signature;
- exact issuer and audience;
- expiry.

To preserve an existing connector, a useful deployment pattern is a second OAuth-only hostname routed through the same tunnel to the same `127.0.0.1:8787` origin. Set Cloudflare ingress `httpHostHeader` to the existing `PUBLIC_MCP_URL` hostname so FastMCP's host allowlist does not need to expand.

Do not persist OAuth client secrets, access tokens, refresh tokens, or raw application JWTs in Git or operator documentation.

## Generic external mode

Use generic external mode for a VPS reverse proxy, Tailscale Funnel, another tunnel provider, or a connector lifecycle intentionally managed outside this project.

```text
PUBLIC_ACCESS_MODE=external
EXTERNAL_TUNNEL_PROVIDER=manual
PUBLIC_MCP_URL=https://terminalbridge.example.com/mcp
```

```bash
uv run terminalbridge start --mode external
```

The operator starts only the review and MCP services. The external proxy or connector remains manually managed.

## URL validation

`PUBLIC_MCP_URL` must:

- use `https://`;
- contain a hostname;
- use the `/mcp` endpoint;
- exclude query parameters, fragments, usernames, passwords, and access tokens.

Keep the access token in `MCP_ACCESS_TOKEN`. The token is added only when copying the real connector URL.

## Configure and operate

Run the interactive setup:

```bash
uv run terminalbridge setup
```

Then use the same commands for every mode:

```bash
uv run terminalbridge doctor
uv run terminalbridge start
uv run terminalbridge status
uv run terminalbridge logs
uv run terminalbridge restart
uv run terminalbridge stop
```

Force a saved mode transition when needed:

```bash
uv run terminalbridge start --mode ngrok
uv run terminalbridge start --mode cloudflare
uv run terminalbridge start --mode external
```

The command preserves provider-specific details while switching. For example, changing temporarily to ngrok does not delete the saved Cloudflare config and tunnel name.

Print a redacted URL or copy the real tokenized URL locally:

```bash
uv run terminalbridge mcp-url
uv run terminalbridge copy-url
```

Expected connector form:

```text
https://terminalbridge.example.com/mcp?access_token=<TOKEN>
```

The MCP server also accepts `Authorization: Bearer <TOKEN>`, while the documented ChatGPT connector workflow continues to support the query-token URL.

## Move one shared domain between computers

A fixed domain may be used on Mac, Linux, or Windows, but its connector must be active on only one computer at a time. If the ChatGPT connector URL must remain unchanged, configure the same `MCP_ACCESS_TOKEN` privately on those computers; do not transmit it through command arguments, logs, chat, or Git.

To move from Mac to Windows:

1. Stop the complete Mac stack:

   ```bash
   uv run terminalbridge stop
   ```

2. Confirm the Mac public connector is stopped.
3. Start the Windows stack with the same user-owned tunnel configuration:

   ```powershell
   uv run terminalbridge start
   uv run terminalbridge status
   ```

4. Keep the ChatGPT connector URL unchanged.
5. Confirm that reads and proposals now target the Windows workspace.

Running replica connectors on multiple computers can distribute related requests across different local workspaces. That is not a supported default workflow.

On Windows, an interactive terminal or an operating-system service/task may be needed when the connector must survive logout or an SSH session ending. The project does not automatically install a persistent scheduled task for every user.

## Process safety

Managed Cloudflare state is stored under the user's runtime process directory:

```text
cloudflared.pid
cloudflared.log
cloudflared.process.json
```

Before stopping a recorded PID, the operator verifies that the running process still matches the saved cloudflared command. If the PID has been reused by an unrelated process, it removes only stale tracking files and does not terminate that process.

The operator also prevents its managed ngrok and Cloudflare connectors from running at the same time. It cannot stop an independently started connector on another computer, so the one-active-computer rule still matters.

## Security requirements

- Keep `MCP_ACCESS_TOKEN` private and outside Git.
- Keep ngrok authtokens and Cloudflare credentials outside the repository.
- Do not place a token inside `PUBLIC_MCP_URL`.
- Treat every public endpoint as internet-reachable.
- Keep DNS-rebinding host checks enabled.
- Keep the review UI bound to loopback.
- Approve proposals only on the computer currently serving the public domain.
- Never copy one user's tunnel credentials into a distributable package.

## Diagnostics

```bash
uv run terminalbridge doctor
uv run terminalbridge status
uv run terminalbridge logs mcp
uv run terminalbridge logs cloudflared
uv run terminalbridge mcp-url
```

Use low-level commands only when diagnosing one Bridge component:

```bash
uv run woojae status
uv run woojae restart mcp
uv run woojae logs ngrok
```
