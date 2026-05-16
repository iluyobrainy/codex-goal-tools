---
description: Set, view, pause, resume, complete, or clear the active native Codex thread goal.
---

# /goal-native

Bridge this slash command to Codex's native `thread/goal/*` app-server backend.

## UI Sync Priority

If the current Codex thread exposes native goal tools, use them first for the pieces they support because they emit the live event that updates the Desktop goal pill immediately:

- `get_goal` for status.
- `create_goal` for a new active goal when no goal exists.
- `update_goal` with `status: "complete"` for genuine completion.

Use the Python bridge for `setup`, `pause`, `resume`, `clear`, `compact`, `auto-compact`, and for leaving the paused `Waiting for next goal.` placeholder after a goal completes. The bridge will use the running Desktop app-server proxy when its control socket is available, otherwise it falls back to a direct app-server process.

## Arguments

- No arguments, `show`, or `status`: show the current native goal.
- `set <objective>` or any other free-form text: set the native goal objective and ensure 200k auto-compaction is active.
- `pause`: pause the native goal.
- `resume`: resume the native goal and ensure 200k auto-compaction is active.
- `complete`: mark the native goal complete, then leave a paused `Waiting for next goal.` placeholder so the goal lane stays ready for the next objective.
- `clear`: clear the native goal.
- `compact`: start native context compaction for the current thread.
- `auto-compact`: start native context compaction only when the current thread has an active goal.

`setup`, `bootstrap`, `set`, and `resume` enable Codex's native goals feature and add native auto-compaction defaults unless `--no-auto-compact` is used.

## Workflow

1. Parse the text after `/goal-native`.
2. Use the current workspace as `--workspace`.
3. Run the matching command with Python:

```powershell
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py status --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py set --workspace C:\Users\LENOVO\Desktop\iqoption --goal "<objective>"
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py pause --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py resume --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py complete --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py clear --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py auto-compact --workspace C:\Users\LENOVO\Desktop\iqoption
```

## Verification

After every operation, report whether the JSON output includes `_native_goal_backend: true`. Report `_app_server_transport` when it is present: `proxy` is live Desktop transport, `direct` is backend state transport. For `set`, include the native `objective`, `status`, `tokensUsed`, and `timeUsedSeconds` fields.

For `compact` and `auto-compact`, report whether `_native_compact_backend: true` and `compactStarted: true` are present. If `compactDeferred: true` is returned, report it as a graceful non-blocking result and continue the goal. If `compactStarted` is false for another reason, show the returned reason. Native compaction is a Codex turn and is safest at an idle checkpoint before continuing goal work.

When `complete` returns `waitingForNextGoal: true`, treat the previous goal as genuinely completed and the current paused placeholder as a parking state for the user's next goal. If native tools are available, complete through `update_goal` first, then use the bridge to park the placeholder.

## Summary

Keep the response short. State whether the native backend was reached and what goal state is active.
