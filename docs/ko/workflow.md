# 권장 로컬 작업 흐름

이 문서는 ChatGPT에서 Ouroboros Workspace Bridge를 사용할 때의 기본 작업 흐름을 설명합니다.

기본 목표는 일반 로컬 작업에서 ChatGPT MCP tool call 자체를 피하는 것입니다. ChatGPT는 일반 assistant message로 `ouroboros-intent` fenced block을 출력하고, browser companion이 이를 local HTTP로 가져옵니다.

## 일반 로컬 작업 흐름

1. ChatGPT는 MCP tool을 호출하지 않습니다.

2. ChatGPT는 실행 intent block을 일반 assistant message로 출력합니다.

   권장 prototype UX는 아래 local browser companion을 사용합니다.

   ```text
   browser/ouroboros-companion.user.js
   ```

   companion은 ChatGPT 페이지에서 `intent_kind: "run"`이 포함된 `ouroboros-intent` fenced block만 감지합니다.

3. companion은 JSON intent를 local HTTP endpoint로 POST합니다.

   ```text
   http://127.0.0.1:8790/intents/import
   ```

4. local review server가 intent를 검증하고 pending command bundle로 가져옵니다.

5. companion이 기존 pending review UI를 열거나 focus합니다.

   주요 route:

   ```text
   /pending
   /pending?bundle_id=<bundle_id>
   /review-intent?token=...
   /review-intent/preview?token=...
   /intents/import
   ```

6. 로컬 UI에서 bundle을 승인합니다. 설정된 approval mode가 허용하면 Safe Auto 또는 YOLO가 처리할 수 있습니다.

   Safe Auto와 YOLO는 로컬 승인 동작만 바꿉니다. ChatGPT가 따라야 할 기본 흐름은 그대로 read-only intent와 local pending UI입니다.

7. bundle-focused page에서 최종 상태를 확인합니다.

   `/pending?bundle_id=<bundle_id>`는 `pending`, `applied`, `failed`, `rejected` 상태의 bundle을 모두 보여줍니다. 이 화면에는 compact한 `Copy for ChatGPT` JSON 블록이 있습니다.

8. 실행 완료 뒤 `/handoffs/latest` 또는 handoff queue가 결과를 companion에 전달합니다.

9. companion은 handoff 메시지를 ChatGPT composer에 준비합니다. 기본값으로 자동 전송하지 않습니다.

10. 사용자가 준비된 메시지를 전송하면 ChatGPT가 결과를 받아 다음 작업을 이어갑니다.

## 상태 이어가기 우선순위

로컬 승인 또는 실행 뒤에는 아래 순서를 사용합니다.

1. `/handoffs/latest` 기반 companion handoff
2. `workspace_next_handoff`
3. bundle page의 `Copy for ChatGPT` JSON
4. `workspace_list_handoffs`
5. `workspace_recover_last_activity`는 디버깅 또는 중단된 호출 조사에만 사용

`workspace_recover_last_activity`는 tool call이 MCP server에 도달했는지 불확실할 때 여전히 유용하지만, 일반 continuation 경로는 아닙니다.

## Tool 우선순위

권장 tool 우선순위:

1. 일반 assistant message의 `ouroboros-intent` block + local companion
2. local pending UI 승인
3. handoff queue
4. read-only signed intent tools는 fallback 또는 편의 도구
5. submit-first tools는 durable MCP ack가 명시적으로 필요할 때만 사용
6. `workspace_stage_*_and_wait` tools는 legacy 또는 편의 fallback
7. primitive stage tools는 public MCP schema에 노출되면 안 됨

fallback tool 우선순위:

1. read-only signed intent flow + local pending UI
2. handoff queue
3. submit-first tools
4. `workspace_stage_*_and_wait` tools는 legacy 또는 편의 fallback
5. primitive stage tools는 public MCP schema에 노출되면 안 됨

submit-first tools는 기본 경로가 아닙니다. ChatGPT web이 MCP tool call 자체에 approval modal을 띄울 수 있기 때문입니다. 그래도 직접 durable bundle ack가 명시적으로 필요할 때는 사용할 수 있습니다.

```text
workspace_submit_command_bundle
workspace_submit_action_bundle
workspace_submit_patch_bundle
workspace_submit_commit_bundle
```

긴 wait wrapper를 기본 경로로 쓰지 마세요. 하나의 ChatGPT tool call을 오래 열어 두기 때문에 더 취약합니다.

## Local Companion Prototype

첫 companion prototype은 userscript입니다.

```text
browser/ouroboros-companion.user.js
```

Tampermonkey 같은 userscript manager로 설치할 수 있습니다.

하는 일:

- ChatGPT 페이지에서 language name이 `ouroboros-intent`인 fenced code block을 감지합니다.
- 유효한 intent JSON을 `http://127.0.0.1:8790/intents/import`로 POST합니다.
- `http://127.0.0.1:8790/pending?bundle_id=<bundle_id>`를 열거나 focus합니다.
- `http://127.0.0.1:8790/handoffs/latest`를 polling합니다.
- `bundle_id`, `status`, `ok`, `next`, `stdout_tail`, `stderr_tail`를 담은 ChatGPT 메시지를 준비합니다.
- composer 입력이 어려우면 handoff 메시지를 clipboard에 복사합니다.

실행 intent block:

````md
```ouroboros-intent
{
  "version": 1,
  "intent_kind": "run",
  "intent_type": "check",
  "cwd": "Custom-Tools/GPT-Tools/my-terminal-tool",
  "params": {
    "check": "git_status"
  }
}
```
````

문서나 설명 예시에서는 가능하면 `ouroboros-intent`가 아니라 일반 `json` fence를 사용하세요. companion은 `intent_kind: "run"`이 있는 block만 import하므로, 이 필드가 없는 설명용 JSON은 자동 import하지 않습니다.

하지 않는 일:

- local pending approval을 우회하지 않습니다.
- 기본값으로 ChatGPT 메시지를 자동 전송하지 않습니다.
- 임의의 code block을 가져오지 않습니다.
- `intent_kind: "run"`이 없는 설명용 JSON은 가져오지 않습니다.
- 정상 흐름에서 수동 Intent Inbox를 요구하지 않습니다.

보안 참고:

- `http://127.0.0.1:8790`에만 요청합니다.
- 로컬 테스트 목적으로 직접 바꾸는 경우가 아니라면 `autoSubmit`은 꺼진 상태로 둡니다.
- 가져온 bundle은 기존처럼 local review UI에서 승인하거나 거절합니다.

## Intent Inbox

`/pending`의 Intent Inbox는 고급 fallback입니다.

companion을 사용할 수 없거나 fallback인 read-only signed intent tools를 사용해 ChatGPT가 `local_review_url`을 반환했을 때 사용합니다. 다음 중 하나를 붙여넣을 수 있습니다.

- 전체 local URL
- raw intent token

같은 intent를 다시 가져와도 중복 bundle을 만들지 않고 같은 bundle로 redirect합니다.

read-only signed intent tools는 fallback 또는 편의 도구로 유지됩니다.

```text
workspace_prepare_check_intent
workspace_prepare_commit_current_changes_intent
workspace_prepare_dev_session_intent
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
- local companion이 `intent_kind: "run"`을 포함한 `ouroboros-intent` block을 수동 copy/paste 없이 import한다.
- 설명용 `json` block 또는 `intent_kind: "run"`이 없는 `ouroboros-intent` block은 import하지 않는다.
- read-only check intent가 pending UI로 import된다.
- YOLO가 즉시 적용한 bundle도 `/pending?bundle_id=<bundle_id>`에서 보인다.
- bundle-focused page에 `Copy for ChatGPT` JSON이 보인다.
- 로컬 실행 뒤 `workspace_next_handoff`가 최신 handoff를 반환한다.
- local checks가 통과하고 `npx`가 없을 때 `bash scripts/check_all.sh`가 exit `0`으로 끝난다.

### 지원하는 companion action intent

companion JSON import 경로는 현재 다음 실행용 `intent_type` 값을 허용합니다.

- `check`
- `commit_current_changes`
- `dev_session`
- `apply_patch`
- `write_file`
- `run_script`
- `command_bundle`

마지막 네 가지는 ChatGPT가 MCP bundle tool을 직접 호출하지 않고 일반 `ouroboros-intent` 메시지만 출력해도 browser companion이 로컬 pending UI로 가져올 수 있게 하기 위한 타입입니다.
