# 공개 연결 모드

Ouroboros Workspace Bridge는 하나의 공통 MCP·review 코어를 세 가지 운영 모드로 실행합니다. 권장 명령은 다음과 같습니다.

```bash
uv run terminalbridge setup
uv run terminalbridge start
uv run terminalbridge status
```

`uv run woojae ...`는 디버깅과 하위 호환을 위한 저수준 Bridge supervisor 명령으로 계속 사용할 수 있습니다.

OS 서비스 매니저에서 운영할 때는 `start`를 주기적으로 다시 실행하는 polling 대신 전체 스택을 하나의 foreground lifecycle로 실행합니다.

```bash
uv run terminalbridge supervise
```

`supervise`는 계속 실행되면서 정상 review/MCP/tunnel child를 재사용하고, 종료된 child를 회수(reap)한 뒤 누락된 관리 프로세스만 다시 시작합니다. macOS launchd 같은 서비스 매니저는 이 foreground 프로세스를 자체 재시작 정책으로 관리하면 됩니다(`RunAtLoad` + `KeepAlive`). 따라서 `StartInterval` polling은 필요하지 않습니다. `terminalbridge stop`은 supervisor를 유지한 채 관리 child를 명시적 정지 상태로 두며, `terminalbridge start`가 정상 supervision을 다시 시작합니다.

## 사용자별 소유 원칙

각 설치는 반드시 해당 사용자가 소유한 인프라를 사용합니다.

- 사용자 자신의 `MCP_ACCESS_TOKEN`
- 사용자 자신의 ngrok 계정과 도메인
- 또는 사용자 자신의 Cloudflare 계정, 도메인, tunnel, config와 credential

저장소에는 관리자의 실제 token, tunnel credential, tunnel ID, 공개 도메인 또는 사용자별 절대 경로가 작동 기본값으로 포함되지 않습니다. 문서의 도메인은 예시입니다.

## ngrok 모드

ngrok은 기존 설치와 호환되는 기본 모드입니다.

```text
PUBLIC_ACCESS_MODE=ngrok
NGROK_HOST=<선택형-고정-ngrok-도메인>
```

명시적으로 시작하거나 저장된 모드를 사용합니다.

```bash
uv run terminalbridge start --mode ngrok
# 또는
uv run terminalbridge start
```

운영 명령이 다음을 시작하고 관리합니다.

- localhost review UI
- 로컬 MCP 서버
- 사용자의 ngrok connector

`NGROK_HOST`가 비어 있으면 ngrok 임시 URL을 사용할 수 있습니다. ChatGPT connector URL을 안정적으로 유지하려면 고정 ngrok host가 필요합니다.

## 관리형 Cloudflare 모드

사용자가 자신의 Cloudflare 계정에 named tunnel과 공개 hostname을 만들어 둔 경우 Cloudflare 모드를 선택합니다.

Bridge 하위 호환 설정은 external을 유지하고, operator provider가 Cloudflare lifecycle 관리를 선택합니다.

```text
PUBLIC_ACCESS_MODE=external
EXTERNAL_TUNNEL_PROVIDER=cloudflare
PUBLIC_MCP_URL=https://terminalbridge.example.com/mcp
CLOUDFLARED_CONFIG_PATH=~/.cloudflared/terminalbridge.yml
CLOUDFLARED_TUNNEL_NAME=my-terminalbridge
CLOUDFLARED_BIN=cloudflared
```

명시적으로 시작하거나 저장된 모드를 사용합니다.

```bash
uv run terminalbridge start --mode cloudflare
# 또는
uv run terminalbridge start
```

운영 명령이 다음을 시작하고 관리합니다.

- localhost review UI
- 로컬 MCP 서버
- 사용자가 설정한 `cloudflared` connector

Cloudflare config는 사용자의 공개 hostname을 다음 로컬 MCP 주소에만 연결해야 합니다.

```text
http://127.0.0.1:8787
```

Review UI는 절대 공개하지 마세요.

```text
http://127.0.0.1:8790/pending
```

Cloudflare 계정 로그인, tunnel 생성, DNS route, credential 저장과 config 소유권은 각 사용자의 책임입니다. 프로젝트는 사용자가 지정한 connector를 시작하고 중지하는 역할만 합니다.

### 선택형 Cloudflare Access Managed OAuth

OAuth를 지원하는 MCP client에는 기존 `MCP_ACCESS_TOKEN`을 URL에 전달하는 대신 Cloudflare Access Managed OAuth를 추가할 수 있습니다. 이 기능은 기존 정적 token 인증을 대체하지 않고 **추가 인증 경로**로 동작하므로, 기존 ChatGPT connector와 OAuth client가 같은 로컬 MCP 서버를 공유할 수 있습니다.

원본에서 Access JWT 검증을 활성화하려면 두 값을 함께 설정합니다.

```text
CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
CLOUDFLARE_ACCESS_AUDIENCE=<access-application-aud>
```

두 값 중 하나만 설정된 상태는 fail-closed로 거부됩니다. 둘 다 설정되지 않으면 기존 `MCP_ACCESS_TOKEN` 동작만 유지합니다.

Managed OAuth를 사용할 때는 Cloudflare Access self-hosted application을 MCP hostname/path에 적용하고, 해당 application의 정확한 AUD와 team domain을 Bridge runtime 설정에 저장합니다. Cloudflare가 인증 후 원본에 전달하는 `Cf-Access-Jwt-Assertion`은 FastMCP 도달 전에 다음을 검증합니다.

- RS256 및 `kid`
- Cloudflare team의 rotating JWKS 서명
- 정확한 issuer와 audience
- 만료 시간

기존 connector를 깨지 않으려면 같은 tunnel과 같은 `127.0.0.1:8787` origin을 사용하되 OAuth client용 별도 hostname을 두는 구성이 유용합니다. 이 경우 Cloudflare ingress의 `httpHostHeader`를 기존 `PUBLIC_MCP_URL` hostname으로 유지하면 FastMCP의 host allowlist를 넓히지 않아도 됩니다.

OAuth client secret, Access token, refresh token, application JWT 원문은 runtime 문서나 Git에 저장하지 않습니다.

## 일반 external 모드

VPS reverse proxy, Tailscale Funnel, 다른 tunnel provider 또는 프로젝트 밖에서 관리하려는 connector에는 일반 external 모드를 사용합니다.

```text
PUBLIC_ACCESS_MODE=external
EXTERNAL_TUNNEL_PROVIDER=manual
PUBLIC_MCP_URL=https://terminalbridge.example.com/mcp
```

```bash
uv run terminalbridge start --mode external
```

운영 명령은 review와 MCP만 시작하며 외부 proxy 또는 connector는 사용자가 별도로 관리합니다.

## URL 검증 규칙

`PUBLIC_MCP_URL`은 다음 조건을 만족해야 합니다.

- `https://` 사용
- hostname 포함
- `/mcp` endpoint 사용
- query, fragment, username, password, access token 미포함

Access token은 `MCP_ACCESS_TOKEN`에 보관합니다. 실제 connector URL을 복사할 때만 token이 추가됩니다.

## 설정과 운영

대화형 설정을 실행합니다.

```bash
uv run terminalbridge setup
```

모드와 관계없이 같은 명령으로 운영합니다.

```bash
uv run terminalbridge doctor
uv run terminalbridge start
uv run terminalbridge status
uv run terminalbridge logs
uv run terminalbridge restart
uv run terminalbridge stop
```

필요하면 모드를 명시적으로 전환하고 저장할 수 있습니다.

```bash
uv run terminalbridge start --mode ngrok
uv run terminalbridge start --mode cloudflare
uv run terminalbridge start --mode external
```

모드를 전환해도 provider별 세부값은 보존됩니다. 예를 들어 잠시 ngrok으로 바꾸더라도 저장된 Cloudflare config와 tunnel 이름은 삭제되지 않습니다.

마스킹된 URL을 확인하거나 실제 token URL을 로컬 clipboard로 복사합니다.

```bash
uv run terminalbridge mcp-url
uv run terminalbridge copy-url
```

Connector 주소 형식:

```text
https://terminalbridge.example.com/mcp?access_token=<TOKEN>
```

MCP 서버는 `Authorization: Bearer <TOKEN>` 요청도 허용하며, 문서화된 ChatGPT connector 흐름에서는 query-token URL도 계속 지원합니다.

## 여러 컴퓨터 사이에서 공유 도메인 전환

고정 도메인을 Mac, Linux, Windows에서 사용할 수 있지만 connector는 한 번에 한 컴퓨터에서만 활성화해야 합니다. ChatGPT connector URL을 그대로 유지하려면 해당 컴퓨터들에 같은 `MCP_ACCESS_TOKEN`을 비공개로 설정해야 하며, command argv·로그·채팅·Git을 통해 전달하면 안 됩니다.

Mac에서 Windows로 옮기는 예시:

1. Mac의 전체 연결 스택을 중지합니다.

   ```bash
   uv run terminalbridge stop
   ```

2. Mac의 공개 connector가 중지됐는지 확인합니다.
3. 같은 사용자 소유 tunnel 설정을 가진 Windows에서 시작합니다.

   ```powershell
   uv run terminalbridge start
   uv run terminalbridge status
   ```

4. ChatGPT connector URL은 그대로 유지합니다.
5. 읽기와 proposal이 Windows workspace를 대상으로 하는지 확인합니다.

여러 컴퓨터에서 replica connector를 동시에 실행하면 연속 요청이 서로 다른 로컬 workspace로 분산될 수 있습니다. 기본 지원 방식이 아닙니다.

Windows에서 logout이나 SSH 연결 종료 후에도 connector를 유지해야 한다면 대화형 터미널 대신 운영체제 service 또는 Task Scheduler가 필요할 수 있습니다. 프로젝트는 모든 사용자에게 영구 예약 작업을 자동 설치하지 않습니다.

## 프로세스 안전성

관리형 Cloudflare 상태는 사용자 runtime process 디렉터리에 저장됩니다.

```text
cloudflared.pid
cloudflared.log
cloudflared.process.json
```

기록된 PID를 종료하기 전에 실제 실행 프로세스가 저장된 cloudflared 명령과 일치하는지 확인합니다. PID가 다른 프로세스에 재사용된 경우 추적 파일만 정리하고 관련 없는 프로세스는 종료하지 않습니다.

운영 명령은 자신이 관리하는 ngrok과 Cloudflare connector가 동시에 실행되지 않도록 처리합니다. 다만 다른 컴퓨터에서 별도로 실행한 connector까지 자동으로 중지할 수는 없으므로 단일 활성 컴퓨터 원칙은 계속 중요합니다.

## 보안 요구사항

- `MCP_ACCESS_TOKEN`을 비공개로 유지하고 Git 밖에 저장합니다.
- ngrok authtoken과 Cloudflare credential을 저장소 밖에 둡니다.
- `PUBLIC_MCP_URL` 안에 token을 넣지 않습니다.
- 모든 공개 endpoint를 인터넷에서 접근 가능한 주소로 취급합니다.
- DNS rebinding host 검사를 유지합니다.
- Review UI를 loopback에만 bind합니다.
- 현재 공개 도메인을 제공하는 컴퓨터에서만 proposal을 승인합니다.
- 특정 사용자의 tunnel credential을 배포 패키지에 포함하지 않습니다.

## 진단

```bash
uv run terminalbridge doctor
uv run terminalbridge status
uv run terminalbridge logs mcp
uv run terminalbridge logs cloudflared
uv run terminalbridge mcp-url
```

Bridge 구성요소 하나를 저수준에서 진단할 때만 다음 명령을 사용합니다.

```bash
uv run woojae status
uv run woojae restart mcp
uv run woojae logs ngrok
```
