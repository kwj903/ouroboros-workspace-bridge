# ChatGPT 에이전트 지침

이 문서는 ChatGPT에서 Ouroboros Workspace Bridge 기반 로컬 개발을 안전하게 진행하기 위한 프로젝트 지침 템플릿입니다.

아래 `Project Instructions` 블록을 ChatGPT 프로젝트 지침에 그대로 복사해서 사용할 수 있습니다.

## 사용 방법

1. ChatGPT에서 이 로컬 개발용 프로젝트를 엽니다.
2. 프로젝트 지침 편집 화면으로 이동합니다.
3. 아래 `Project Instructions` 블록 전체를 복사합니다.
4. 프로젝트 지침에 붙여넣습니다.
5. 새 채팅을 열고 Ouroboros Workspace Bridge 작업을 진행합니다.

## Project Instructions

```md
# Project Instructions: ChatGPT 에이전트사용

이 프로젝트의 주 작업 대상은 로컬 Ouroboros Workspace Bridge 기반 개발이다.
작업의 핵심 목표는 로컬 파일 수정, 테스트, 커밋을 안전하고 검증 가능한 단위로 진행하는 것이다.

## Critical: Ouroboros Workspace Bridge 안전 규칙

Ouroboros Workspace Bridge를 사용할 때는 아래 규칙을 최우선으로 따른다.

- 기본 public mutation 경로는 목적별 proposal wrapper를 사용한다.
- 파일 수정은 `workspace_propose_file_replace_and_wait` 또는 `workspace_propose_file_write_and_wait`를 사용한다.
- 검증 명령은 `workspace_propose_command_and_wait`를 사용한다.
- patch, commit, push는 각각 `workspace_propose_patch_and_wait`, `workspace_propose_git_commit_and_wait`, `workspace_propose_git_push_and_wait`를 사용한다.
- 하나의 proposal은 하나의 파일 수정, 명령, patch, commit, push만 수행한다.
- 파일 수정, 테스트, git add, git commit, push를 절대 하나의 proposal에 섞지 않는다.
- 커밋 proposal에는 테스트나 precheck 명령을 섞지 않는다.
- pending bundle을 만든 뒤에는 사용자 승인/거부와 bundle status 확인 전까지 다음 mutation bundle을 만들지 않는다.
- 효율성보다 안전한 단계 분리가 우선이다.
- 불필요한 tool call을 늘리지 않는다. 짧은 수정에는 payload ref를 사용하지 않는다.

## Mutation tool 호출 전 self-check

Ouroboros Workspace Bridge mutation tool을 호출하기 직전에 반드시 점검한다.

- 이번 bundle의 목적이 한 문장으로 설명 가능한가?
- 목적별 proposal wrapper를 사용하고 있는가?
- 파일 수정, 테스트, 커밋, push가 섞여 있지 않은가?
- precheck_commands를 쓰고 있지 않은가?
- pending proposal 승인/거부 확인 전 새 mutation proposal을 만들고 있지 않은가?
- 짧은 수정인데 불필요하게 `workspace_stage_text_payload`를 쓰고 있지 않은가?
- 긴 patch, 긴 old_text/new_text, 긴 bash 명령을 직접 넣고 있지 않은가?

하나라도 아니면 tool call을 만들지 말고 더 작은 단계로 쪼갠다.

## Payload ref 사용 기준

`workspace_stage_text_payload`는 긴 텍스트를 안전하게 다루기 위한 예외용 도구다.
기본 파일 수정 흐름에서는 사용하지 않는다.

짧은 수정에는 payload ref를 사용하지 않는다.

예:

- README 링크 1줄 추가
- 짧은 문단 교체
- import 한 줄 추가
- 설정값 몇 줄 수정
- 테스트 코드 일부 추가
- 2KB 이하의 `old_text` / `new_text`

이런 경우에는 `workspace_propose_file_replace_and_wait` 또는 `workspace_propose_file_write_and_wait` 같은 목적별 proposal wrapper에 `content`, `old_text`, `new_text`를 직접 넣는다.

payload ref를 사용하는 경우:

- 긴 파일 전체 생성
- 긴 문서 대규모 교체
- 긴 unified diff patch
- 긴 `old_text` / `new_text` 교체
- tool call JSON이 커져 ChatGPT UI나 MCP 승인 UI가 멈출 가능성이 있는 작업

권장 기준:

- 2KB 이하: payload ref 사용 금지
- 2KB~8KB: 가능하면 직접 action bundle 사용
- 8KB 이상: payload ref 고려
- 20KB 이상 또는 큰 patch: payload ref 우선

주의:

- payload ref도 별도 tool call이므로 불필요하게 쓰면 응답 중단 가능성이 높아진다.
- 짧은 수정에서는 payload ref보다 직접 단일 action bundle이 더 안전하다.
- payload ref를 만들었지만 응답이 끊긴 경우, 먼저 `workspace_list_command_bundles`와 `workspace_git_status`를 확인한다.
- payload ref 생성만으로는 프로젝트 파일이 수정되지 않는다.

## 표준 작업 흐름

읽기/확인 작업은 직접 수행해도 된다.

- `workspace_git_status`
- `workspace_read_file`
- `workspace_read_many_files`
- `workspace_search_text`
- `workspace_command_bundle_status`
- `workspace_list_command_bundles`

파일 수정 흐름:

1. git status 확인
2. 관련 파일 읽기
3. 수정 크기 판단
   - 짧은 수정: payload ref 없이 action bundle 생성
   - 긴 본문/긴 patch: payload ref 사용 고려
4. 파일 수정 bundle 생성
   - action 1개만 포함
5. bundle status 확인
6. 사용자 승인 대기
7. 승인 후 bundle status 확인
8. git status 확인

검증 흐름:

1. command bundle 생성
   - step 1개만 포함
2. 사용자 승인 대기
3. 승인 후 bundle status 확인
4. 다음 검증이 필요하면 별도 bundle로 진행

커밋 흐름:

1. 수정 적용 확인
2. 필요한 검증 확인
3. git status 확인
4. 커밋 전용 bundle 생성
5. 사용자 승인 대기
6. 승인 후 bundle status 확인
7. 최종 git status 확인

## 금지 패턴

다음은 금지한다.

- 여러 actions를 한 bundle에 넣기
- 여러 steps를 한 command bundle에 넣기
- 파일 수정 + 테스트를 같은 bundle에 넣기
- 테스트 + 커밋을 같은 bundle에 넣기
- 파일 수정 + 커밋을 같은 bundle에 넣기
- 긴 `bash -lc`에 여러 명령을 묶기
- 긴 patch나 긴 old_text/new_text를 직접 tool call에 넣기
- pending bundle이 있는데 다음 mutation bundle을 만드는 것
- 검증 명령 여러 개를 하나의 command bundle에 넣는 것

큰 텍스트나 큰 patch가 필요하면:

- `workspace_stage_text_payload`를 먼저 사용한다.
- bundle에는 payload ref만 넣는다.
- 또는 더 작은 파일/patch 단위로 나눈다.

긴 검증이 필요하면:

- 먼저 `scripts/check_*.sh` 또는 `scripts/check_*.py`를 작은 수정 bundle로 만든다.
- 그 다음 command bundle에서 해당 스크립트 하나만 실행한다.

## 실수 복구 규칙

실수로 큰 bundle 또는 배열 길이 2 이상 bundle을 만들었다면:

1. 사용자가 승인하지 않도록 안내한다.
2. 새 작업을 진행하지 않는다.
3. `workspace_list_command_bundles` 또는 `workspace_command_bundle_status`로 확인한다.
4. pending 상태이면 cancel/reject한다.
5. `workspace_git_status`로 작업 트리를 확인한다.
6. 단일 작업 bundle로 다시 만든다.

## 응답 규칙

bundle을 만든 뒤에는 반드시 다음을 알려준다.

- 생성된 bundle ID
- 승인 위치
- 승인 후 확인할 항목
- 실패 시 확인할 status/log 명령

사용자가 “진행해줘”, “직접 해줘”라고 해도 큰 bundle을 만들지 않는다.
항상 작은 bundle 생성 → status 확인 → 사용자 승인 → status 확인 순서로 진행한다.

## 로컬 세션 제어

Ouroboros Workspace Bridge 관련 로컬 프로세스 제어는 `woojae` CLI를 우선 사용한다.

- `uv run woojae start`
- `uv run woojae status`
- `uv run woojae doctor`
- `uv run woojae logs [review|mcp|ngrok]`
- `uv run woojae restart [mcp|ngrok]`
- `uv run woojae stop`

UI나 프로세스 제어 기능을 새로 만들 때는 먼저 CLI에서 검증하고, 그 다음 UI에 연결한다.

## 보안

토큰, API key, access token, Bearer token, ngrok token, `.env` 값은 출력하지 않는다.
비밀값이 포함될 수 있는 출력은 마스킹하거나 요약한다.
README, 로그, 테스트 fixture, 스크린샷, 응답에 비밀값을 남기지 않는다.
```

## 사용 예시

프로젝트 지침을 넣은 뒤에는 다음처럼 요청하면 좋습니다.

```text
현재 상태를 확인하고 다음 작업을 작은 bundle 단위로 진행해줘.
```

```text
승인했어. bundle status와 git status를 확인한 뒤 다음 단계로 진행해.
```

```text
이번에는 파일 수정만 하고, 테스트와 커밋은 별도 bundle로 나눠줘.
```

## 승인 전 확인 체크리스트

로컬 review UI에서 bundle을 승인하기 전에 확인하세요.

- 작업 목적이 하나인가?
- action 또는 step이 하나인가?
- 파일 수정, 테스트, 커밋이 섞여 있지 않은가?
- 예상한 파일만 바꾸는가?
- 비밀값이 포함되어 있지 않은가?

하나라도 애매하면 승인하지 말고 ChatGPT에게 bundle을 취소하고 더 작게 나누라고 요청하세요.
