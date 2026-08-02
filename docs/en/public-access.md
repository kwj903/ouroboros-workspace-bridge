# Public access modes

Ouroboros Workspace Bridge supports two ways to expose the local MCP endpoint to ChatGPT.

## ngrok mode

`ngrok` is the default and preserves the original workflow.

```text
PUBLIC_ACCESS_MODE=ngrok
NGROK_HOST=<optional-fixed-ngrok-domain>
```

`uv run woojae start` manages:

- the localhost review UI;
- the local MCP server;
- ngrok.

If `NGROK_HOST` is empty, ngrok may use a temporary URL. A fixed host is required for `uv run woojae copy-url`.

## External mode

Use `external` when you already manage an HTTPS domain through Cloudflare Tunnel, a VPS reverse proxy, or another connector.

```text
PUBLIC_ACCESS_MODE=external
PUBLIC_MCP_URL=https://terminalbridge.woojae.dev/mcp
```

`PUBLIC_MCP_URL` must:

- use `https://`;
- include the `/mcp` endpoint;
- exclude query parameters, fragments, usernames, passwords, and access tokens.

`uv run woojae start` manages only:

- the localhost review UI;
- the local MCP server.

The external tunnel or reverse proxy remains operator-managed. Route the public hostname only to:

```text
http://127.0.0.1:8787
```

Never publish the review UI:

```text
http://127.0.0.1:8790/pending
```

## Configure

Run:

```bash
uv run woojae setup
```

Choose `external`, then enter:

```text
https://terminalbridge.woojae.dev/mcp
```

Verify without exposing the token:

```bash
uv run woojae doctor
uv run woojae status
uv run woojae mcp-url
```

Copy the real token-protected connector URL only to your local clipboard:

```bash
uv run woojae copy-url
```

Expected connector form:

```text
https://terminalbridge.woojae.dev/mcp?access_token=<TOKEN>
```

The bridge also accepts `Authorization: Bearer <TOKEN>` requests, but the documented ChatGPT connector workflow continues to use the query-token URL.

## Move the shared domain between computers

Use the same public domain on Mac, Linux, or Windows, but run its connector on only one computer at a time.

To move from Mac to Windows:

1. Stop the Mac bridge:

   ```bash
   uv run woojae stop
   ```

2. Stop the Mac external tunnel connector.
3. Start the Windows bridge:

   ```powershell
   uv run woojae start
   uv run woojae status
   ```

4. Start the same external tunnel connector on Windows.
5. Keep the ChatGPT connector URL unchanged.
6. Confirm that reads and proposals now target the Windows workspace.

Running replicas on multiple computers can send related requests to different local workspaces. That is not a supported default workflow.

## Security requirements

- Keep `MCP_ACCESS_TOKEN` private and outside Git.
- Do not place the token inside `PUBLIC_MCP_URL`.
- Treat the public endpoint as internet-reachable.
- Keep DNS-rebinding host checks enabled.
- Keep the review UI bound to loopback.
- Approve proposals only on the computer currently serving the shared domain.
- Do not store Cloudflare or tunnel credentials in this repository.

## Diagnostics

```bash
uv run woojae doctor
uv run woojae status
uv run woojae logs mcp
uv run woojae mcp-url
```

In external mode, `doctor` does not require ngrok and `status` reports ngrok as disabled. The bridge validates the configured URL but cannot start or repair the external tunnel itself.
