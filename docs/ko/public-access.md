# 공개 연결 모드

Ouroboros Workspace Bridge는 로컬 MCP endpoint를 ChatGPT에 공개하는 두 가지 방식을 지원합니다.

## ngrok 모드

`ngrok`은 기본값이며 기존 동작을 그대로 유지합니다.

```text
PUBLIC_ACCESS_MODE=ngrok
NGROK_HOST=<선택형-고정-ngrok-도메인>
```

`uv run woojae start`가 다음 서비스를 관리합니다.

- localhost review UI
- 로컬 MCP 서버
- ngrok

`NGROK_HOST`가 비어 있으면 ngrok 임시 URL을 사용할 수 있습니다. `uv run woojae copy-url`로 고정 연결 URL을 복사하려면 고정 host가 필요합니다.

## external 모드

Cloudflare Tunnel, VPS reverse proxy 또는 다른 connector로 HTTPS 도메인을 직접 관리한다면 `external` 모드를 사용합니다.

```text
PUBLIC_ACCESS_MODE=external
PUBLIC_MCP_URL=https://terminalbridge.woojae.dev/mcp
```

`PUBLIC_MCP_URL` 규칙:

- `https://`를 사용해야 합니다.
- `/mcp` endpoint를 포함해야 합니다.
- query, fragment, username, password, access token을 포함하면 안 됩니다.

`uv run woojae start`가 관리하는 서비스는 다음 두 개뿐입니다.

- localhost review UI
- 로컬 MCP 서버

외부 tunnel 또는 reverse proxy는 사용자가 별도로 관리합니다. 공개 hostname은 다음 origin에만 연결하세요.

```text
http://127.0.0.1:8787
```

다음 review UI는 절대 공개하지 마세요.

```text
http://127.0.0.1:8790/pending
```

## 설정

다음을 실행합니다.

```bash
uv run woojae setup
```

`external`을 선택하고 다음 주소를 입력합니다.

```text
https://terminalbridge.woojae.dev/mcp
```

token을 노출하지 않고 상태를 확인합니다.

```bash
uv run woojae doctor
uv run woojae status
uv run woojae mcp-url
```

실제 token-protected connector URL은 로컬 clipboard에만 복사합니다.

```bash
uv run woojae copy-url
```

예상 연결 주소:

```text
https://terminalbridge.woojae.dev/mcp?access_token=<TOKEN>
```

서버는 `Authorization: Bearer <TOKEN>` 요청도 지원하지만, 현재 문서화된 ChatGPT connector 흐름은 query token URL을 계속 사용합니다.

## 여러 컴퓨터 사이에서 공유 도메인 인계하기

같은 공개 도메인을 Mac, Linux, Windows에서 사용할 수 있지만 connector는 한 번에 한 컴퓨터에서만 실행해야 합니다.

Mac에서 Windows로 옮기는 순서:

1. Mac bridge를 종료합니다.

   ```bash
   uv run woojae stop
   ```

2. Mac의 external tunnel connector를 종료합니다.
3. Windows bridge를 시작합니다.

   ```powershell
   uv run woojae start
   uv run woojae status
   ```

4. Windows에서 동일한 external tunnel connector를 시작합니다.
5. ChatGPT connector URL은 변경하지 않습니다.
6. 파일 조회와 proposal이 Windows workspace를 대상으로 실행되는지 확인합니다.

여러 컴퓨터에서 replica connector를 동시에 실행하면 서로 연관된 요청이 다른 workspace로 분산될 수 있습니다. 기본 사용 흐름에서는 지원하지 않습니다.

## 보안 요구사항

- `MCP_ACCESS_TOKEN`은 Git 밖에서 비공개로 관리합니다.
- token을 `PUBLIC_MCP_URL` 안에 넣지 않습니다.
- 공개 endpoint는 인터넷에서 접근 가능한 주소로 취급합니다.
- DNS rebinding host 검사를 유지합니다.
- review UI를 loopback에만 바인딩합니다.
- 공유 도메인을 현재 제공하는 컴퓨터에서만 proposal을 승인합니다.
- Cloudflare 또는 tunnel credential을 이 저장소에 보관하지 않습니다.

## 진단

```bash
uv run woojae doctor
uv run woojae status
uv run woojae logs mcp
uv run woojae mcp-url
```

external 모드에서는 `doctor`가 ngrok 설치를 요구하지 않으며 `status`는 ngrok이 비활성화됐다고 표시합니다. Bridge는 설정된 URL을 검증하지만 외부 tunnel 자체를 시작하거나 복구하지는 않습니다.
