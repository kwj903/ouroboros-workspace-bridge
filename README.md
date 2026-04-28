# Workspace Terminal Bridge

ChatGPT에서 로컬 `~/workspace` 아래의 프로젝트를 안전하게 탐색하고, 수정하고, 검증하기 위한 개인용 MCP 서버입니다.

이 프로젝트의 핵심 목표는 ChatGPT와 대화하면서 로컬 프로젝트를 함께 개발하되, 실제 파일 수정과 명령 실행은 로컬 review UI에서 사용자가 승인한 뒤 적용되도록 만드는 것입니다.

## 핵심 기능

- `~/workspace` 내부 파일/디렉터리 탐색
- UTF-8 텍스트 파일 읽기, 생성, 수정, append
- patch 미리보기와 승인 기반 적용
- Git status/diff 확인과 승인 기반 commit
- 허용된 명령 프로필 실행
- command/action/patch bundle 기반 로컬 승인 워크플로우
- 큰 텍스트 payload를 runtime에 저장하고 ref로 참조하는 안전한 대용량 수정 흐름
- operation, audit, backup, trash, task 기록

## 현재 상태

이 서버는 개인 로컬 개발용 MVP입니다.

기본 작업 루트:

```text
~/workspace
```

런타임 데이터 위치:

```text
~/.mcp_terminal_bridge/my-terminal-tool
```

런타임 데이터에는 audit log, backup, trash, operation record, task record, command bundle, text payload가 포함됩니다.

## 빠른 시작

프로젝트 디렉터리로 이동합니다.

```bash
cd ~/workspace/Custom-Tools/GPT-Tools/my-terminal-tool
```

환경과 세션 상태를 점검합니다.

```bash
scripts/dev_session.sh doctor
```

전체 로컬 세션을 시작합니다.

```bash
scripts/dev_session.sh start
```

상태를 확인합니다.

```bash
scripts/dev_session.sh status
```

로컬 승인 UI:

```text
http://127.0.0.1:8790/pending
```

작업을 마치면 세션을 종료합니다.

```bash
scripts/dev_session.sh stop
```

자세한 세션 운영 방법은 [`docs/user/local-session.md`](docs/user/local-session.md)를 참고하세요.

## 문서 구조

사용자용 문서:

- [`docs/user/local-session.md`](docs/user/local-session.md): 로컬 세션 시작, 상태 확인, review UI, MCP/ngrok 연결, ChatGPT 앱 Refresh 기준
- [`docs/user/troubleshooting.md`](docs/user/troubleshooting.md): review UI, MCP, ngrok, bundle 상태 문제 복구 절차
- [`docs/user/chatgpt-agent-usage.md`](docs/user/chatgpt-agent-usage.md): ChatGPT 프로젝트 지침에 바로 복사해 넣을 수 있는 Workspace Terminal Bridge 작업 지침 템플릿

프로젝트 작업용 문서:

- [`docs/project/development-workflow.md`](docs/project/development-workflow.md): action/command/patch bundle, payload ref, 검증, 커밋, 안전한 개발 흐름
- [`docs/project/phase-6-release-checklist.md`](docs/project/phase-6-release-checklist.md): Phase 6 로컬 세션 관리 기능 완료 범위와 릴리즈 확인 항목
- [`docs/project/phase-7-plan.md`](docs/project/phase-7-plan.md): Phase 7 안정성, 관측성, 운영성 개선 계획

## 프로젝트 구조

```text
my-terminal-tool/
├── data/
├── docs/
│   ├── project/
│   └── user/
├── scripts/
├── terminal_bridge/
├── tests/
├── main.py
├── pyproject.toml
├── README.md
├── server.py
└── uv.lock
```

주요 구성:

- `server.py`: FastMCP entrypoint와 MCP tool registration layer
- `terminal_bridge/`: runtime 경로, safety, payload, bundle, patch, task, operation helper
- `scripts/`: review UI, command bundle runner/watcher, local session helper, smoke check
- `tests/`: safety, bundle workflow, review UI helper 테스트
- `docs/user/`: 앱 사용자를 위한 운영 문서
- `docs/project/`: 프로젝트 유지보수와 개발 작업 문서

## 요구 사항

현재 확인된 개발 환경:

```text
macOS
Python 3.12+
uv
ngrok
ChatGPT Developer Mode App
```

Python 의존성은 `pyproject.toml` 기준입니다.

```toml
dependencies = [
    "mcp[cli]>=1.27.0",
    "pydantic>=2.13.3",
]
```

## 운영 원칙

이 프로젝트는 로컬 파일을 실제로 수정할 수 있으므로 다음 원칙을 지킵니다.

- 토큰 값은 README, 로그, 응답, `.env`에 넣지 않습니다.
- `MCP_ACCESS_TOKEN`, Bearer token, ngrok token 같은 비밀값은 개인 shell secrets 또는 runtime env에서 관리합니다.
- 프로젝트 `.env`에 토큰을 만들거나 저장하지 않습니다.
- 읽기, 검색, git status, bundle status 확인은 read-only 도구로 먼저 수행합니다.
- 파일 생성/수정/명령 실행은 로컬 승인 bundle을 거쳐 적용합니다.
- 큰 텍스트는 `workspace_stage_text_payload`로 runtime에 저장한 뒤 ref로 참조합니다.
- 파일 수정, 테스트, 커밋은 작은 단계로 분리합니다.

개발 작업의 자세한 규칙은 [`docs/project/development-workflow.md`](docs/project/development-workflow.md)를 참고하세요.

## 검증

일반적인 전체 검증:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

문서만 바꾼 경우에는 보통 다음으로 충분합니다.

```bash
git diff --check
```

변경 유형별 검증 기준은 [`docs/project/development-workflow.md`](docs/project/development-workflow.md)의 Verification 섹션을 참고하세요.

## 보안 주의

ngrok URL은 외부에서 접근 가능한 주소입니다. 작업하지 않을 때는 ngrok과 MCP 서버를 꺼두는 것을 권장합니다.

```bash
scripts/dev_session.sh stop
```

토큰을 바꾸거나 MCP tool schema를 변경한 경우에는 MCP 서버를 재시작하고 ChatGPT 앱에서 MCP 연결을 Refresh해야 합니다.

자세한 연결/복구 절차는 다음 문서를 참고하세요.

- [`docs/user/local-session.md`](docs/user/local-session.md)
- [`docs/user/troubleshooting.md`](docs/user/troubleshooting.md)
