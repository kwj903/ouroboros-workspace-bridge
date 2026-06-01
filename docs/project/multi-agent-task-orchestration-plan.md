# Multi-Agent Task Orchestration Upgrade Plan

이 문서는 Workspace Terminal Bridge를 여러 ChatGPT 채팅 세션, 여러 AI 웹앱, 또는 여러 에이전트 작업이 동시에 안전하게 사용할 수 있도록 발전시키기 위한 프로젝트 업그레이드 계획이다.

`docs/project/`는 개발 방향, 유지보수 원칙, 릴리즈/업그레이드 계획을 남기는 위치이므로 이 계획을 보관하기에 적절하다. 사용자용 사용법이 안정화되면 필요한 부분만 `docs/ko/`와 `docs/en/`의 사용자 문서로 옮긴다.

## 현재 판단

현재 구조는 하나의 MCP server와 하나의 runtime root를 여러 클라이언트가 공유한다.

```text
여러 ChatGPT / AI 앱
  -> 하나의 MCP server
  -> 하나의 runtime root
  -> 하나의 command_bundles queue
  -> 하나의 approval mode
  -> 하나의 latest handoff stream
```

이 구조는 단일 작업에는 단순하고 효과적이다. 그러나 여러 채팅 세션 또는 여러 AI 앱이 동시에 붙어 서로 다른 프로젝트나 같은 프로젝트를 병렬 작업할 때는 다음 문제가 생길 수 있다.

- pending bundle이 전역 queue에 섞인다.
- `workspace_next_handoff`가 전역 최신 handoff를 반환해 다른 세션 결과를 가져올 수 있다.
- approval mode가 전역이라 한 세션의 YOLO 설정이 다른 세션 bundle에도 영향을 줄 수 있다.
- 같은 프로젝트나 같은 파일을 동시에 수정하면 충돌이 원본 작업공간에서 직접 발생할 수 있다.
- bundle JSON write와 상태 이동이 atomic/lock 기반이 아니라 여러 runner나 review server가 같은 runtime을 볼 때 race 가능성이 있다.

## 목표

Codex류 에이전트 도구의 관리 방식처럼 여러 작업을 병렬로 진행하되, 각 작업을 독립 task workspace에서 처리하고 원본 프로젝트 통합은 사람이 검토하도록 만든다.

핵심 목표:

- 단일 작업 UX는 현재처럼 유지한다.
- 병렬 작업은 task별 isolated workspace에서 진행한다.
- 여러 ChatGPT/AI 앱 결과가 섞이지 않도록 `client_id`, `session_id`, `task_id`, `project_id`를 기록한다.
- handoff와 history는 bundle/task/project/client 기준으로 조회할 수 있게 한다.
- YOLO/Safe Auto approval mode는 전역이 아니라 task/project/client scope로 제한할 수 있게 한다.
- 같은 프로젝트의 최종 통합은 merge queue에서 사람이 diff/test/conflict를 확인한 뒤 승인한다.
- 충돌은 원본 프로젝트를 망가뜨리기 전에 통합 단계에서 감지하고 보류한다.

## 유지할 기본 UX

### 단일 작업

단일 작업은 현재 흐름을 유지한다.

```text
사용자 요청
  -> ChatGPT가 direct proposal bundle 생성
  -> Review UI의 승인 대기에서 확인
  -> 사용자가 승인
  -> 원본 프로젝트에 적용
  -> 테스트/검증
  -> 필요 시 커밋 proposal
```

이 경우 사용자는 task workspace, worktree, merge queue를 몰라도 된다.

### 병렬 작업

같은 프로젝트에서 여러 작업을 동시에 진행하거나 여러 AI 앱이 동시에 작업하는 경우 task workspace mode를 사용한다.

```text
사용자 요청
  -> 작업을 여러 task로 분리
  -> 각 task별 isolated workspace 생성
  -> 각 task workspace에서 수정/테스트
  -> 작업 완료 후 통합 대기 목록으로 이동
  -> 사용자가 diff/test/conflict 확인
  -> 원본 프로젝트에 merge/apply 승인
  -> 최종 테스트
  -> task별 커밋
```

## 권장 UI 구조

UI는 승인 의미가 다른 화면을 분리한다.

```text
승인 대기
작업 보드
통합 대기
이력
설정
```

### 승인 대기

일반 direct proposal을 처리한다.

- 파일 수정 proposal
- 명령 실행 proposal
- 테스트 실행 proposal
- 커밋 proposal
- push proposal

카드에는 다음을 명확히 표시한다.

```text
Mode: Direct
Target: 원본 프로젝트에 바로 적용됨
```

버튼 예:

```text
[승인] [거절] [Diff 보기]
```

### 작업 보드

병렬 task의 진행 상태를 보여준다.

상태 예:

```text
queued
running
waiting_review
tests_failed
ready_to_merge
conflict
discarded
```

카드에는 다음을 표시한다.

```text
task_id
client_id
session_id
project_id
source project
task workspace
status
test summary
conflict summary
```

버튼 예:

```text
[Diff 보기] [로그 보기] [통합 대기로 보내기] [수정 요청] [폐기]
```

### 통합 대기

격리 task workspace에서 완료된 결과를 원본 프로젝트에 통합할지 결정한다.

카드에는 다음을 표시한다.

```text
task title
project
base ref
changed files
test result
conflict status
recommended merge order
```

버튼 예:

```text
[원본에 통합] [통합 전 테스트] [충돌 확인] [보류] [폐기]
```

머지 모드에서는 버튼명을 단순히 `승인`으로 쓰지 않는다. `원본에 통합`처럼 실제 의미가 드러나는 이름을 사용한다.

## 핵심 모델

### Task record

```json
{
  "task_id": "task-...",
  "client_id": "chatgpt-web-1",
  "session_id": "optional-session-id",
  "project_id": "sha256(repo_root)",
  "project_root": "workspace/projects/foo",
  "base_ref": "main",
  "task_workspace": "~/.mcp_terminal_bridge/my-terminal-tool/task_workspaces/task-.../repo",
  "workspace_mode": "direct | task-workspace",
  "status": "queued | running | waiting_review | ready_to_merge | applied | failed | cancelled",
  "created_at": "...",
  "updated_at": "..."
}
```

### Bundle metadata

모든 bundle에는 가능한 한 다음 metadata를 포함한다.

```json
{
  "task_id": null,
  "client_id": "default",
  "session_id": "default",
  "project_id": "sha256(cwd or repo_root)",
  "project_root": "workspace/...",
  "workspace_mode": "direct | task-workspace",
  "source_cwd": "workspace/...",
  "effective_cwd": "workspace/... or task_workspace/..."
}
```

## Task workspace 전략

### Git repository

Git repo는 `git worktree`를 기본 격리 방식으로 사용한다.

```bash
git worktree add <runtime>/task_workspaces/<task_id>/repo <base_ref>
```

각 task는 원본 repo가 아니라 task worktree에서 수정과 테스트를 수행한다.

장점:

- 같은 repo에서 여러 task를 동시에 진행할 수 있다.
- 원본 작업트리를 더럽히지 않는다.
- 실패한 task는 worktree만 제거하면 된다.
- task별 diff와 commit을 만들 수 있다.
- 통합 단계에서 conflict를 명확히 확인할 수 있다.

### Non-git directory

초기 버전에서는 non-git directory에 대해 task workspace mode를 제한하거나, runtime 아래 copy workspace를 fallback으로 사용한다.

```text
runtime/task_workspaces/<task_id>/copy
```

Non-git fallback은 conflict detection과 통합 방식이 복잡하므로 1차 구현에서는 direct mode만 지원해도 된다.

## Approval mode scope

현재 전역 approval mode는 동시 작업에서 위험하다. 다음 scope 구조로 확장한다.

```text
approval_modes/global.json
approval_modes/projects/<project_id>.json
approval_modes/clients/<client_id>.json
approval_modes/tasks/<task_id>.json
```

우선순위:

```text
task > client > project > global
```

권장 기본값:

```text
global: normal
project: normal
task: 명시적으로 설정한 경우에만 safe-auto 또는 yolo
```

YOLO는 task 또는 project scope에서만 권장한다. Global YOLO는 강한 경고를 표시한다.

## Handoff routing

전역 최신 handoff는 동시 세션에서 혼선을 만든다. 다음 조회 방식을 추가한다.

```text
workspace_get_handoff_for_bundle(bundle_id)
workspace_get_latest_handoff_for_task(task_id)
workspace_list_handoffs(task_id=None, project_id=None, client_id=None, session_id=None)
```

기존 `workspace_next_handoff`는 유지하되 전역 최신값임을 명확히 문서화하고, 동시 세션에서는 bundle/task 기준 조회를 권장한다.

## Scheduler, lock, atomicity

동시 사용 안정성을 위해 scheduler와 lock을 추가한다.

### Bundle 상태

```text
pending -> processing -> applied
pending -> processing -> failed
pending -> rejected
```

`processing` 상태를 추가해 같은 bundle이 두 번 실행되는 것을 방지한다.

### Atomic JSON write

현재 단순 write 대신 atomic replace를 사용한다.

```python
write_json_atomic(path, data):
    tmp = path.with_name(f".{path.name}.{pid}.{uuid}.tmp")
    tmp.write_text(...)
    os.replace(tmp, path)
```

### Locks

```text
runtime/locks/bundles/<bundle_id>.lock
runtime/locks/tasks/<task_id>.lock
runtime/locks/repos/<project_id>.lock
runtime/locks/files/<file_key>.lock
```

동작 원칙:

- 같은 bundle은 한 번만 처리한다.
- 같은 task 내부 실행은 직렬화한다.
- task workspace 내부 작업은 병렬 가능하다.
- 원본 repo 통합은 repo lock으로 직렬화한다.
- direct mode에서 같은 파일을 수정하는 bundle은 file lock 또는 conflict check로 보호한다.

## Conflict detection

Direct mode와 merge mode 모두 conflict detection을 강화한다.

File action bundle 생성 시 target snapshot metadata를 기록한다.

```json
{
  "path": "server.py",
  "expected_sha256": "...",
  "expected_mtime_ns": 123,
  "existed": true
}
```

Runner 적용 직전 현재 상태를 재검증한다.

```text
현재 sha256 != expected_sha256
  -> conflict
  -> failed 또는 waiting_conflict
  -> "file changed after proposal was created" 메시지 표시
```

Task workspace merge 단계에서는 원본 repo와 task diff를 비교해 conflict 여부를 표시한다.

## Multi-profile runtime

강한 격리가 필요한 경우 profile 기반 다중 서버를 지원한다.

```bash
uv run woojae start --profile project-a
uv run woojae start --profile project-b
```

각 profile은 별도 값을 가진다.

```text
runtime root
MCP port
review port
ngrok URL
access token
workspace root
```

Task workspace mode는 한 서버 안에서 여러 작업을 관리하는 방식이고, multi-profile은 서버 인스턴스 자체를 분리하는 방식이다. 둘은 상호 보완적이다.

## 구현 단계

### Phase 1: 동시 세션 섞임 방지

목표: 기존 direct workflow를 유지하면서 bundle/handoff/history가 세션별로 구분되도록 만든다.

작업:

1. bundle record에 `task_id`, `client_id`, `session_id`, `project_id`, `workspace_mode` 추가.
2. proposal tools에 optional `task_id`, `client_id`, `session_id` 추가.
3. `workspace_get_handoff_for_bundle(bundle_id)` 추가.
4. `workspace_list_handoffs`와 `workspace_list_command_bundles`에 필터 추가.
5. review UI에 project/task/client badge와 필터 추가.
6. `workspace_next_handoff`는 global latest임을 문서화.

성공 기준:

- 여러 세션이 동시에 bundle을 만들어도 UI에서 구분된다.
- 각 세션은 bundle_id/task_id 기준으로 자기 결과를 가져올 수 있다.
- 기존 단일 작업 flow는 깨지지 않는다.

### Phase 2: Scoped approval mode

목표: 한 세션의 YOLO/Safe Auto 설정이 다른 세션에 영향을 주지 않게 한다.

작업:

1. global/project/client/task approval mode 저장 구조 추가.
2. bundle watcher가 bundle metadata 기준으로 approval mode를 계산.
3. review UI에서 approval scope를 표시하고 설정할 수 있게 함.
4. Global YOLO에 강한 경고 표시.
5. task/project scope의 YOLO를 기본 권장 방식으로 문서화.

성공 기준:

- task-level YOLO가 다른 task bundle을 자동 승인하지 않는다.
- project-level mode가 다른 project에 영향을 주지 않는다.
- global mode 기본값은 normal이다.

### Phase 3: Task workspace mode

목표: 같은 프로젝트에서 여러 작업을 안전하게 병렬 실행한다.

작업:

1. `workspace_task_start_project` 또는 기존 task start 확장.
2. Git repo에 대해 `git worktree` 기반 task workspace 생성.
3. task workspace 대상 command/file/patch proposal 추가.
4. task diff/test/log 조회 도구 추가.
5. task result를 `ready_to_merge` 상태로 올리는 흐름 추가.
6. 작업 보드 UI 추가.

성공 기준:

- 같은 repo에서 task-A/task-B가 각각 별도 worktree에서 수정된다.
- 원본 repo는 통합 전까지 변경되지 않는다.
- task별 diff와 test result를 확인할 수 있다.

### Phase 4: Merge queue / 통합 대기

목표: task 결과를 원본 프로젝트에 안전하게 통합한다.

작업:

1. 통합 대기 UI 추가.
2. task diff, test result, conflict status 표시.
3. `workspace_task_apply_to_project(task_id)` 추가.
4. 원본 repo 통합은 별도 pending proposal로 생성.
5. 통합 후 최종 테스트와 task별 commit flow 지원.

성공 기준:

- ready task를 원본 repo에 apply/merge할 수 있다.
- conflict가 있으면 자동 통합을 막고 보류한다.
- 통합 후 원본 repo 테스트를 실행할 수 있다.

### Phase 5: Scheduler, lock, atomic write

목표: 여러 runner/review server 또는 여러 동시 작업에서 race를 줄인다.

작업:

1. `write_json_atomic` 도입.
2. bundle lock 도입.
3. `processing` 상태 추가.
4. task/repo/file lock 도입.
5. double-apply 방지 테스트 추가.

성공 기준:

- 같은 bundle을 두 runner가 동시에 apply해도 한 번만 실행된다.
- 원본 repo 통합은 직렬화된다.
- atomic write로 깨진 JSON record가 생기지 않는다.

### Phase 6: Direct mode conflict detection

목표: 기존 direct mode에서도 동시 수정 안전성을 높인다.

작업:

1. file action proposal 생성 시 expected sha256/mtime 기록.
2. runner 적용 직전 target 상태 재검증.
3. mismatch 시 conflict로 실패 처리.
4. review UI에 conflict 메시지 표시.

성공 기준:

- proposal 생성 후 파일이 바뀌면 오래된 proposal이 덮어쓰지 않는다.
- conflict 메시지가 사용자가 이해할 수 있게 표시된다.

### Phase 7: Multi-profile runtime

목표: 프로젝트별 또는 팀별로 MCP server 인스턴스 자체를 분리할 수 있게 한다.

작업:

1. `woojae start --profile <name>` 지원.
2. profile별 runtime root, MCP port, review port, token, ngrok 설정 지원.
3. profile별 ChatGPT app setup 안내 출력.
4. docs 업데이트.

성공 기준:

- profile A/B가 서로 다른 runtime과 port를 사용한다.
- 여러 프로젝트를 완전히 분리된 MCP app으로 등록할 수 있다.

## 테스트 계획

필수 테스트:

1. 두 client가 동시에 bundle을 생성해도 `client_id`, `project_id`, `task_id`가 올바르게 기록된다.
2. `workspace_get_handoff_for_bundle(bundle_id)`가 정확한 handoff를 반환한다.
3. handoff/list bundle 필터가 task/project/client 기준으로 동작한다.
4. task-level YOLO가 다른 task를 자동 승인하지 않는다.
5. project-level approval mode가 다른 project bundle에 영향을 주지 않는다.
6. 같은 bundle을 두 runner가 동시에 apply해도 한 번만 실행된다.
7. task worktree가 원본 repo를 변경하지 않고 독립적으로 수정된다.
8. ready task를 merge queue로 올리고 원본 repo에 apply할 수 있다.
9. conflict가 있으면 통합을 막고 conflict 상태를 표시한다.
10. 기존 direct proposal workflow와 전체 테스트가 계속 통과한다.

기본 검증 명령:

```bash
uv run python -m unittest discover -s tests
git diff --check
```

MCP schema나 review UI 변경 후에는 MCP 재시작과 ChatGPT app refresh가 필요하다.

## 사용자 작업 흐름 요약

### 단일 작업

```text
요구사항 말함
  -> direct bundle 생성
  -> 승인 대기에서 승인
  -> 원본 프로젝트 적용
  -> 테스트
  -> 커밋
```

### 병렬 작업

```text
여러 작업을 task로 나눔
  -> 각 task가 isolated workspace에서 작업
  -> 작업 보드에서 상태 확인
  -> 완료된 task가 통합 대기로 이동
  -> diff/test/conflict 확인
  -> 원본에 통합 승인
  -> 최종 테스트
  -> task별 커밋
```

### 여러 AI 앱 동시 사용

```text
ChatGPT / Codex / Claude / Grok 등 각 client가 task 생성
  -> client_id/task_id/project_id로 구분
  -> 각 task workspace에서 독립 작업
  -> 통합 대기에서 사람이 결과를 선택적으로 적용
```

## 최종 기대 효과

- 단일 작업의 간단한 UX는 유지된다.
- 여러 채팅 세션 결과가 handoff/history에서 섞이지 않는다.
- 여러 AI 앱이 같은 MCP server를 공유해도 task/client/project 기준으로 구분된다.
- 같은 프로젝트 병렬 작업이 원본 repo를 직접 망가뜨리지 않는다.
- 충돌은 원본 통합 전 merge queue에서 감지된다.
- YOLO는 전역 위험 설정이 아니라 task/project/client scope로 제한된다.
- 실패한 작업은 task workspace만 폐기하면 된다.
- Codex식 병렬 task 관리 방식을 로컬 Workspace Bridge에 맞게 적용할 수 있다.

## 우선순위 요약

가장 먼저 구현할 것은 대규모 worktree 기능이 아니라 `섞임 방지`다.

```text
1. metadata + filtering
2. bundle/task 기준 handoff routing
3. scoped approval mode
4. task workspace mode
5. merge queue
6. lock/atomicity
7. conflict detection
8. multi-profile runtime
```

이 순서가 기존 사용성을 유지하면서 병렬 에이전트 작업 구조로 확장하는 가장 안전한 경로다.
