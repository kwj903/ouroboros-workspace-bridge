from __future__ import annotations


DEFAULT_PUBLIC_MCP_TOOLS: tuple[str, ...] = (
    "workspace_info",
    "workspace_list",
    "workspace_tree",
    "workspace_read_file",
    "workspace_find_files",
    "workspace_search_text",
    "workspace_read_many_files",
    "workspace_project_snapshot",
    "workspace_git_status",
    "workspace_git_diff",
    "workspace_preview_patch",
    "workspace_transport_probe",
    "workspace_read_audit_log",
    "workspace_recover_last_activity",
    "workspace_get_handoff_for_bundle",
    "workspace_next_handoff",
    "workspace_list_handoffs",
    "workspace_list_tool_calls",
    "workspace_tool_call_status",
    "workspace_list_backups",
    "workspace_stage_text_payload",
    "workspace_propose_command_and_wait",
    "workspace_propose_file_write_and_wait",
    "workspace_propose_file_replace_and_wait",
    "workspace_propose_patch_and_wait",
    "workspace_propose_git_commit_and_wait",
    "workspace_propose_git_push_and_wait",
    "workspace_command_bundle_status",
    "workspace_wait_command_bundle_status",
    "workspace_list_command_bundles",
    "workspace_cancel_command_bundle",
)

DIRECT_MUTATION_MCP_TOOLS: tuple[str, ...] = (
    "workspace_create_directory",
    "workspace_write_file",
    "workspace_append_file",
    "workspace_replace_text",
    "workspace_soft_delete",
    "workspace_move_to_trash",
    "workspace_restore_deleted",
    "workspace_restore_backup",
    "workspace_apply_patch",
    "workspace_git_add",
    "workspace_git_commit",
    "workspace_exec",
    "workspace_run_profile",
)


PUBLIC_MUTATION_TOOL_ANNOTATIONS: dict[str, dict[str, bool]] = {
    "workspace_stage_text_payload": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "workspace_propose_command_and_wait": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
    "workspace_propose_file_write_and_wait": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "workspace_propose_file_replace_and_wait": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "workspace_propose_patch_and_wait": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "workspace_propose_git_commit_and_wait": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "workspace_propose_git_push_and_wait": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
    "workspace_cancel_command_bundle": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
}


def public_mutation_annotations(tool_name: str) -> dict[str, bool]:
    """Return a fresh FastMCP annotation mapping for a public mutating tool."""

    try:
        return dict(PUBLIC_MUTATION_TOOL_ANNOTATIONS[tool_name])
    except KeyError as exc:
        raise ValueError(f"Unknown public mutation tool: {tool_name}") from exc
