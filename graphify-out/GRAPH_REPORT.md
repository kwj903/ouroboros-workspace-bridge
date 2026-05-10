# Graph Report - /Users/kwj903/workspace/Custom-Tools/GPT-Tools/my-terminal-tool  (2026-05-11)

## Corpus Check
- 56 files · ~259,326 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1337 nodes · 8637 edges · 37 communities detected
- Extraction: 24% EXTRACTED · 76% INFERRED · 0% AMBIGUOUS · INFERRED: 6597 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]

## God Nodes (most connected - your core abstractions)
1. `CommandBundleStep` - 162 edges
2. `CommandBundleAction` - 154 edges
3. `CommandBundleStageResult` - 143 edges
4. `CommandBundleStatusResult` - 143 edges
5. `WriteFileResult` - 138 edges
6. `DeleteResult` - 137 edges
7. `CommandResult` - 137 edges
8. `CommandBundleListResult` - 137 edges
9. `OperationStatusResult` - 137 edges
10. `BackupRestoreResult` - 137 edges

## Surprising Connections (you probably didn't know these)
- `command_proposal_step()` --calls--> `CommandBundleStep`  [INFERRED]
  /Users/kwj903/workspace/Custom-Tools/GPT-Tools/my-terminal-tool/terminal_bridge/mcp_tools/proposals.py → terminal_bridge/models.py
- `file_write_proposal_action()` --calls--> `CommandBundleAction`  [INFERRED]
  /Users/kwj903/workspace/Custom-Tools/GPT-Tools/my-terminal-tool/terminal_bridge/mcp_tools/proposals.py → terminal_bridge/models.py
- `file_replace_proposal_action()` --calls--> `CommandBundleAction`  [INFERRED]
  /Users/kwj903/workspace/Custom-Tools/GPT-Tools/my-terminal-tool/terminal_bridge/mcp_tools/proposals.py → terminal_bridge/models.py
- `_validate_intent_token()` --calls--> `import_intent_token()`  [INFERRED]
  /Users/kwj903/workspace/Custom-Tools/GPT-Tools/my-terminal-tool/server.py → terminal_bridge/review_intents.py
- `_prepare_intent()` --calls--> `_resolve_workspace_path()`  [INFERRED]
  /Users/kwj903/workspace/Custom-Tools/GPT-Tools/my-terminal-tool/server.py → terminal_bridge/safety.py

## Hyperedges (group relationships)
- **Approval-Gated Mutation Flow** — readme_chatgpt, readme_local_mcp_bridge, readme_pending_bundle, readme_local_review_ui, en_workflow_bundle_first_mcp_flow [EXTRACTED 1.00]
- **Public Proposal Tool Pattern** — changelog_public_proposal_tools, en_workflow_stage_and_wait_tools, ko_agent_one_proposal_rule, en_rationale_smaller_schemas [EXTRACTED 1.00]
- **Local Runtime Operational Stack** — en_local_session_commands, readme_local_review_ui, readme_local_mcp_bridge, en_quickstart_ngrok_setup, en_runtime_data_outside_repo [EXTRACTED 1.00]
- **Safe Public Mutation Workflow** — development_workflow_read_only_inspection, development_workflow_purpose_specific_proposal_wrappers, development_workflow_file_edit_proposals, development_workflow_command_proposals, development_workflow_verification_levels, development_workflow_commit_flow, phase_7_plan_default_public_mutation_path [EXTRACTED 1.00]
- **Local Session Operability Flow** — phase_6_release_checklist_local_session_supervisor, phase_6_release_checklist_dev_session_sh, phase_6_release_checklist_servers_processes_page, phase_6_release_checklist_recovery_path, development_workflow_restart_requirements, phase_7_plan_process_management_ux_polish [INFERRED 0.86]
- **Release and Handoff Alignment** — phase_6_release_checklist_manual_release_checks, phase_7_plan_release_workflow_hardening, phase_7_plan_changelog_operator_handoff_hygiene, update_info_update_version_info_script, update_info_recent_commits_snapshot [INFERRED 0.83]
- **Ouroboros Mark Constructed By Snake Biting Tail** — ouroboros_by_KwakWooJae_ouroboros_symbol, ouroboros_by_KwakWooJae_snake, ouroboros_by_KwakWooJae_tail_in_mouth, ouroboros_by_KwakWooJae_circular_loop [EXTRACTED 1.00]
- **Brand Icon Visual Language** — ouroboros_by_KwakWooJae_image, ouroboros_by_KwakWooJae_minimalist_logo_style, ouroboros_by_KwakWooJae_monochrome_palette, ouroboros_by_KwakWooJae_central_black_disc [INFERRED 0.78]
- **Custom App Creation Form** — chatgpt_new_app_setup_app_icon_upload, chatgpt_new_app_setup_name_field, chatgpt_new_app_setup_description_field, chatgpt_new_app_setup_mcp_server_url_field, chatgpt_new_app_setup_oauth_authentication, chatgpt_new_app_setup_create_button [EXTRACTED 1.00]
- **OAuth MCP Configuration Flow** — chatgpt_new_app_setup_mcp_server_url_field, chatgpt_new_app_setup_oauth_authentication, chatgpt_new_app_setup_advanced_oauth_settings [EXTRACTED 1.00]
- **Custom MCP Risk Acceptance** — chatgpt_new_app_setup_custom_mcp_server_warning, chatgpt_new_app_setup_risk_acknowledgement_checkbox, chatgpt_new_app_setup_create_button [INFERRED 0.80]
- **Approval Mode Options** — pending_review_ui_normal_mode, pending_review_ui_safe_auto_mode, pending_review_ui_yolo_mode [EXTRACTED 1.00]
- **YOLO Auto-Approval Policy** — pending_review_ui_yolo_mode, pending_review_ui_pending_bundles, pending_review_ui_blocked_risk_bundles [EXTRACTED 1.00]
- **Review Panel Primary Layout** — pending_review_ui_sidebar_navigation, pending_review_ui_approval_page, pending_review_ui_latest_handoff_card [INFERRED 0.80]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.03
Nodes (115): list_command_bundles(), approval_mode_confirm_html(), audit_event_summary_html(), audit_state(), bool_chip(), bool_label(), bundle_card_html(), bundle_detail_html() (+107 more)

### Community 1 - "Community 1"
Cohesion: 0.35
Nodes (178): BaseModel, AuditLogResult, BackupEntry, BackupListResult, BackupRestoreResult, CommandBundleAction, CommandBundleListEntry, CommandBundleListResult (+170 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (91): build_parser(), command_help_lookup(), CommandHelp, configured_ngrok_host(), copy_mcp_url(), explicit_help_language(), help_summary(), language_from_locale() (+83 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (68): BaseHTTPRequestHandler, current_pending_bundle_ids(), handle_pending_bundle(), load_bundle_id(), load_bundle_record(), pending_bundle_records(), StopEvent, watch_pending_bundles() (+60 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (70): _list_backup_entries(), _ensure_runtime_dirs(), _record_tool_call(), _tool_call_status_result(), _approve_intent(), _approve_intent_endpoint(), _b64url_decode(), _b64url_encode() (+62 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (48): now_iso(), action_failure_message(), action_step_targets(), apply_append_file(), apply_bundle(), apply_command(), apply_patch_step(), apply_replace_text() (+40 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (58): Command Proposals, Commit Flow, Development Workflow, Failed or Interrupted Tool Call Recovery, File Edit Proposals, Hidden Internal and Advanced Tools, Patch Proposals, Payload Ref Rationale (+50 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (43): _backup_file(), _read_backup_manifest(), _restore_backup_payload(), _sha256_file(), _is_safe_visible_path(), _iter_visible_paths(), _list_workspace(), _read_workspace_file() (+35 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (26): _begin_operation(), _complete_operation(), _emit_audit(), _fail_operation(), _model_to_dict(), _new_operation_id(), _normalize_operation_id(), _operation_path() (+18 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (11): _intent_approved_html(), _review_intent_endpoint(), workspace_prepare_check_intent(), workspace_prepare_commit_current_changes_intent(), workspace_stage_patch_bundle(), command_bundle_file_count(), CommandBundleDedupeTests, IntentFlowTests (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (18): workspace_propose_git_push_and_wait(), workspace_stage_command_bundle_and_wait(), _workspace_stage_command_bundle_and_wait_impl(), StageAndWaitWrapperTests, ToolCallJournalTests, hash_args(), _is_large_content_key(), _is_sensitive_key() (+10 more)

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (19): _argv_has_dangerous_command(), bundle_touches_sensitive_path(), is_safe_auto_eligible(), load_approval_mode(), _looks_sensitive_path(), normalize_approval_mode(), _now_iso(), save_approval_mode() (+11 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (19): _add_children_older_than(), category_paths(), cleanup_candidates(), cleanup_runtime(), CleanupCandidate, CleanupError, CleanupResult, _delete_path() (+11 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (20): _bundle_risk_rank(), _canonical_request_json(), _canonicalize_request_value(), _command_bundle_dirs(), _command_bundle_path(), _find_command_bundle(), _find_command_bundle_by_request_key(), _move_command_bundle() (+12 more)

### Community 14 - "Community 14"
Cohesion: 0.07
Nodes (29): Cross-Platform Python Session Supervisor, Purpose-Specific Public Proposal Tools, Keep Local Mutation Behind Approval Bundles, Contributing Coding Rules, Contributing Verification Checks, Payload Refs, ChatGPT Agent Project Instructions, Approval Modes (+21 more)

### Community 15 - "Community 15"
Cohesion: 0.13
Nodes (12): _new_text_payload_id(), _normalize_text_payload_id(), _serialize_text_payload_field(), _stage_text_payload_chunk(), _text_payload_dir(), _text_payload_manifest_path(), _validate_text_payload_ref(), _read_staged_text_payload() (+4 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (21): _audit(), _read_task_record(), _task_result(), workspace_task_finish(), workspace_task_log_step(), workspace_task_start(), workspace_task_status(), workspace_task_update_plan() (+13 more)

### Community 17 - "Community 17"
Cohesion: 0.16
Nodes (15): _serialize_action_steps(), _serialize_command_steps(), _serialize_commit_command_step(), _serialize_commit_steps(), _validate_git_commit_message(), _validate_git_commit_paths(), _combined_bundle_risk(), _classify_exec_command() (+7 more)

### Community 18 - "Community 18"
Cohesion: 0.16
Nodes (19): Active Mode Badge, Approval Mode Selector, Approval Page, Auto-Approval Warning Banner, Blocked-Risk Bundles, Completed Bundle cmd-20260502-084616-271af9dd, Current Mode Button, View Full History Link (+11 more)

### Community 19 - "Community 19"
Cohesion: 0.14
Nodes (14): Runtime Storage Inspection Commands, No Auth Direct MCP URL, Official ngrok Downloads Page, ngrok Setup, Rationale: Token-Bearing URL Avoids OAuth Setup, Rationale: Keep Secrets and Runtime State Outside Repository, Runtime Data Outside Repository, Temporary ngrok URL Mode (+6 more)

### Community 20 - "Community 20"
Cohesion: 0.23
Nodes (5): _resolve_workspace_root(), _runtime_root(), _session_env_value(), _workspace_root_value(), ConfigWorkspaceRootTests

### Community 21 - "Community 21"
Cohesion: 0.24
Nodes (4): _extract_bearer_token(), _extract_query_token(), _is_authorized_mcp_request(), TokenAuthTests

### Community 22 - "Community 22"
Cohesion: 0.29
Nodes (8): UpdateVersionInfoTests, check_update_info(), git_lines(), main(), normalize_for_check(), recent_commits(), render_update_info(), sanitize_git_text()

### Community 23 - "Community 23"
Cohesion: 0.29
Nodes (11): Advanced OAuth Settings Panel, App Icon Upload, Create Button, Custom MCP Server Risk Warning, Description Field, Guide Link, MCP Server URL Field, Name Field (+3 more)

### Community 24 - "Community 24"
Cohesion: 0.22
Nodes (5): command_proposal_step(), file_replace_proposal_action(), file_write_proposal_action(), git_push_proposal(), validate_git_remote_or_branch()

### Community 25 - "Community 25"
Cohesion: 0.22
Nodes (10): Central Black Disc, Circular Loop Composition, Cycle And Eternity Symbolism, Eclipse Motif, Ouroboros by KwakWooJae Image, Minimalist Logo Style, Black And Light Neutral Palette, Ouroboros Symbol (+2 more)

### Community 26 - "Community 26"
Cohesion: 0.42
Nodes (8): cancel_command_bundle(), command_bundle_status(), command_bundle_status_from_record(), stage_action_bundle_and_wait(), stage_command_bundle_and_wait(), stage_commit_bundle_and_wait(), stage_patch_bundle_and_wait(), wait_command_bundle_status()

### Community 27 - "Community 27"
Cohesion: 0.36
Nodes (2): workspace_info(), ToolSurfaceTests

### Community 28 - "Community 28"
Cohesion: 0.33
Nodes (6): Internal Module Map, terminal_bridge/mcp_runtime.py, terminal_bridge/review_intents.py, terminal_bridge/review_layout.py, scripts/command_bundle_review_server.py, server.py

### Community 29 - "Community 29"
Cohesion: 0.5
Nodes (4): Full Session Restart Fix, Restart Helper Process Group Rationale, schedule_full_session_restart(), subprocess.Popen start_new_session=True

### Community 30 - "Community 30"
Cohesion: 0.67
Nodes (1): Workspace Terminal Bridge package.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (2): Korean setup-ui Onboarding, setup-ui Browser Onboarding

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (2): Setup-Time Help Language Preference, Korean Help Language Setup

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): KwakWooJae Non-Commercial License 1.0

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Stable Write Test

## Knowledge Gaps
- **67 isolated node(s):** `CommandHelp`, `Backward-compatible adapter for the old dev_session helper commands.`, `Return a minimal child-process environment for workspace commands.      Secret-b`, `setup-ui Browser Onboarding`, `KwakWooJae Non-Commercial License 1.0` (+62 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 31`** (2 nodes): `Korean setup-ui Onboarding`, `setup-ui Browser Onboarding`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `Setup-Time Help Language Preference`, `Korean Help Language Setup`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `install.ps1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `dev_session.ps1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `KwakWooJae Non-Commercial License 1.0`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Stable Write Test`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `embedded_watcher_config()` connect `Community 3` to `Community 0`, `Community 4`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `start_service()` connect `Community 2` to `Community 4`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `ReviewServerHelperTests` connect `Community 0` to `Community 3`, `Community 13`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 160 inferred relationships involving `CommandBundleStep` (e.g. with `AccessTokenMiddleware` and `Return basic information about the configured WORKSPACE_ROOT and enabled tools.`) actually correct?**
  _`CommandBundleStep` has 160 INFERRED edges - model-reasoned connections that need verification._
- **Are the 152 inferred relationships involving `CommandBundleAction` (e.g. with `AccessTokenMiddleware` and `Return basic information about the configured WORKSPACE_ROOT and enabled tools.`) actually correct?**
  _`CommandBundleAction` has 152 INFERRED edges - model-reasoned connections that need verification._
- **Are the 141 inferred relationships involving `CommandBundleStageResult` (e.g. with `AccessTokenMiddleware` and `Return basic information about the configured WORKSPACE_ROOT and enabled tools.`) actually correct?**
  _`CommandBundleStageResult` has 141 INFERRED edges - model-reasoned connections that need verification._
- **Are the 141 inferred relationships involving `CommandBundleStatusResult` (e.g. with `AccessTokenMiddleware` and `Return basic information about the configured WORKSPACE_ROOT and enabled tools.`) actually correct?**
  _`CommandBundleStatusResult` has 141 INFERRED edges - model-reasoned connections that need verification._