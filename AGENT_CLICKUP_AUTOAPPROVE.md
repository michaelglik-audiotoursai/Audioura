# Make the agents work the ClickUp queue without per-call approval (2026-06-23)

Each agent prompts before every ClickUp call because its MCP config doesn't pre-approve those tools. Add an **`autoApprove`** array to the ClickUp server entry in each agent's MCP config, then restart/reconnect. No wildcard exists yet — tools are listed by name.

We auto-approve the **read + normal queue-write** tools and deliberately leave **`clickup_delete_task` OUT**, so deletes still require a human OK.

## Tools to auto-approve
```
clickup_get_workspace_hierarchy, clickup_get_list, clickup_get_task,
clickup_get_task_comments, clickup_filter_tasks, clickup_search,
clickup_create_task, clickup_update_task, clickup_move_task,
clickup_create_comment, clickup_attach_task_file, clickup_add_task_link
```
(Intentionally excluded: `clickup_delete_task`.)

---

## Kiro (Mobile + Services)
File: `.kiro/settings/mcp.json` (workspace) or `~/.kiro/settings/mcp.json` (user-wide).
Add `autoApprove` to the **existing** ClickUp server block (don't create a second one):

```json
{
  "mcpServers": {
    "clickup": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.clickup.com/mcp"],
      "disabled": false,
      "autoApprove": [
        "clickup_get_workspace_hierarchy", "clickup_get_list", "clickup_get_task",
        "clickup_get_task_comments", "clickup_filter_tasks", "clickup_search",
        "clickup_create_task", "clickup_update_task", "clickup_move_task",
        "clickup_create_comment", "clickup_attach_task_file", "clickup_add_task_link"
      ]
    }
  }
}
```
Then reload MCP (Kiro: command palette → reconnect MCP servers, or restart Kiro).

## Amazon Q (CLI / Mac Mini)
File: `~/.aws/amazonq/mcp.json` (global) or `.amazonq/mcp.json` (workspace).
Add `autoApprove` (Q also honors a `trusted` array with the same list):

```json
{
  "mcpServers": {
    "clickup": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.clickup.com/mcp"],
      "disabled": false,
      "autoApprove": [
        "clickup_get_workspace_hierarchy", "clickup_get_list", "clickup_get_task",
        "clickup_get_task_comments", "clickup_filter_tasks", "clickup_search",
        "clickup_create_task", "clickup_update_task", "clickup_move_task",
        "clickup_create_comment", "clickup_attach_task_file", "clickup_add_task_link"
      ]
    }
  }
}
```
Then restart `q chat` (or in-session run `/tools trust` for the same tools). Note: if the server is slow to start, `--trust-tools` at launch can fail to apply — editing `mcp.json` is the reliable path.

## Notes
- The server-entry key may already be named something other than `clickup` in their config — add `autoApprove` to whatever the existing ClickUp entry is called; don't duplicate it.
- Keep `clickup_delete_task` out so destructive deletes stay manual.
- Safer-still option: auto-approve only the read tools (get/filter/search/hierarchy) and leave create/update/move/comment as prompts. Use that if you want to watch what they write for now.
