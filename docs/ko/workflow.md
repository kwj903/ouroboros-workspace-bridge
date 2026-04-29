# 권장 로컬 작업 흐름

이 문서는 ChatGPT에서 Ouroboros Workspace Bridge를 사용할 때의 기본 작업 흐름을 설명합니다.

현재 기본값은 bundle-first MCP 흐름입니다. ChatGPT가 durable bundle을 제출하고, 실제 파일 수정, 명령 실행, 커밋은 local review UI에서 승인된 뒤에만 일어납니다. 이전 browser companion / `ouroboros-intent` prototype은 중단되었으며 정상 흐름으로 문서화하지 않습니다.

## 일반 로컬 작업 흐름

1. 필요하면 read-only tool로 workspace를 확인합니다.

   예:

   ```text
   workspace_git_status
   workspace_read_file
   workspace_search_text
   workspace_project_snapshot
   ```

2. local approval을 위한 bundle을 제출합니다.

   권장 public bundle tools:

   ```text
   workspace_submit_command_bundle
   workspace_submit_action_bundle
   workspace_submit_patch_bundle
   workspace_submit_commit_bundle
   ```

   이 도구들은 pending bundle record를 만들고 빠르게 반환합니다. 자체적으로 project change를 적용하지 않습니다.

   File action bundle은 `WORKSPACE_ROOT` 아래 non-git directory에서도 실행할 수 있습니다. 더 이상 `git status` 기반 clean-worktree preflight를 요구하지 않으며, file action rollback은 적용 전 file snapshot을 사용합니다.

3. 로컬에서 검토하고 승인합니다.

   local pending review UI:

   ```text
   /pending
   /pending?bundle_id=<bundle_id>
   ```

   bundle-focused page는 `pending`, `applied`, `failed`, `rejected` 상태의 bundle을 모두 보여줍니다. 이 화면에는 compact한 `Copy for ChatGPT` JSON 블록이 있습니다.

4. 결과를 이어갑니다.

   권장 continuation 순서:

   ```text
   workspace_next_handoff
   workspace_list_handoffs
   Copy for ChatGPT JSON
   workspace_command_bundle_status
   workspace_recover_last_activity
   ```

   `workspace_recover_last_activity`는 일반 continuation이 아니라 debug 또는 interrupted call 조사에 사용합니다.

## Tool 우선순위

권장 순서:

1. Read-only inspection tools
2. Submit-first bundle tools
3. Local pending review UI approval
4. Handoff queue
5. Read-only signed intent tools는 fallback 또는 편의 도구
6. `workspace_stage_*_and_wait` tools는 legacy 또는 편의 fallback
7. Primitive stage tools는 public MCP schema에 노출되면 안 됨

`workspace_stage_*_and_wait` wrapper는 local approval을 기다리는 동안 하나의 ChatGPT tool call을 계속 열어 둡니다. approval/status wait timeout 상한은 45초입니다. 일반 작업에는 submit-first tools와 handoff/status 확인을 우선 사용하세요.

## Signed Intent Fallback

Read-only signed intent tools는 유지됩니다.

```text
workspace_prepare_check_intent
workspace_prepare_commit_current_changes_intent
workspace_prepare_dev_session_intent
```

이 도구들은 signed `local_review_url`을 반환합니다. 로컬 브라우저에서 URL을 열면 intent가 같은 pending bundle approval flow로 import됩니다.

`/pending`의 advanced Intent Inbox는 다음을 받을 수 있습니다.

- 전체 `local_review_url`
- raw signed intent token

Import는 idempotent합니다. 같은 token을 다시 가져오면 가능한 경우 같은 bundle로 redirect합니다.

## 중단된 Companion Prototype

browser companion / `ouroboros-intent` block prototype은 더 이상 지원 workflow가 아닙니다.

의존하지 말아야 할 항목:

```text
browser/ouroboros-companion.user.js
ouroboros-intent fenced blocks
JSON POST imports to /intents/import
```

`/intents/import`는 signed token form import 용도로만 유지됩니다. JSON companion import는 의도적으로 거부됩니다.

## UI Routes

주요 local routes:

```text
/pending
/pending?bundle_id=<bundle_id>
/review-intent?token=...
/review-intent/preview?token=...
/intents/import
/handoffs/latest
```

## Handoff Records

bundle이 final 상태에 도달하면 local runner가 compact handoff record를 아래 경로에 씁니다.

```text
~/.mcp_terminal_bridge/my-terminal-tool/handoffs
```

각 record는 다음 필드를 포함합니다.

```text
handoff_id
bundle_id
status
ok
risk
title
cwd
next
stdout_tail
stderr_tail
created_at
updated_at
```

stdout/stderr tail은 compact하게 저장되며 token처럼 보이는 값은 redaction됩니다.

## 로컬 환경 참고

`bash scripts/check_all.sh`는 local checks를 먼저 실행합니다.

remote MCP Inspector check가 설정되어 있어도 `npx`가 없으면 다음 메시지를 출력하고 skip합니다.

```text
Remote MCP smoke skipped: npx not found on PATH.
```

local checks가 통과했다면 이 skip은 성공으로 처리됩니다. remote MCP Inspector check를 사용하려면 Node.js/npm을 설치하세요.

## 회귀 체크리스트

이 workflow가 정상이라고 보기 전에 수동으로 확인할 항목:

- `/pending`에 page-level horizontal scroll이 없다.
- Intent Inbox가 고급 section 아래에 접힌 상태로 있다.
- Submit-first bundle tools가 변경을 적용하지 않고 pending bundle을 만든다.
- Pending bundle을 local pending review UI에서 승인하거나 거절할 수 있다.
- YOLO가 즉시 적용한 bundle도 `/pending?bundle_id=<bundle_id>`에서 보인다.
- Bundle-focused page에 `Copy for ChatGPT` JSON이 보인다.
- 로컬 실행 뒤 `workspace_next_handoff`가 최신 handoff를 반환한다.
- Primitive stage tools가 `workspace_info().tools`에 없다.
- `/intents/import`로 들어오는 JSON companion import는 거부된다.
- local checks가 통과하고 `npx`가 없을 때 `bash scripts/check_all.sh`가 exit `0`으로 끝난다.
