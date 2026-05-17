---
description: Set, view, pause, resume, complete, or clear the active native Codex thread goal.
---

# /goal-native

Bridge this slash command to Codex's native `thread/goal/*` app-server backend.

## UI Sync Priority

If the current Codex thread exposes native goal tools, use them for starting visible goals because they emit the live event that updates the Desktop goal pill immediately:

- `get_goal` for status.
- `create_goal` for a new active goal when no goal exists.
- If the current goal is the visible `Waiting for next goal.` placeholder and the user gives the next objective, clear the placeholder through the bridge, then call `create_goal` for the new objective.

Do not call native `update_goal` with `status: "complete"` for normal `/goal-native` completion. Desktop removes the pill when that event is sent. Use the Python bridge `complete` action instead; it records the finished objective in the command output and parks the thread at a visible `Waiting for next goal.` goal so the pill can remain visible.

If a higher-priority active goal instruction requires native `update_goal` with `status: "complete"`, immediately reopen the lane before ending the turn. Use native `create_goal` with objective `Waiting for next goal.` so Desktop shows the pill again. Do not pause this waiting placeholder; paused goals can be hidden by the Desktop UI. If `create_goal` is unavailable, run the bridge `park` action.

Use the Python bridge for `setup`, `pause`, `resume`, `clear`, `compact`, `auto-compact`, and completion-with-waiting-placeholder. The bridge will use the running Desktop app-server proxy when its control socket is available, otherwise it falls back to a direct app-server process.

## Arguments

- No arguments, `show`, or `status`: show the current native goal.
- `set <objective>` or any other free-form text: set the native goal objective without changing compaction settings.
- `pause`: pause the native goal.
- `resume`: resume the native goal without changing compaction settings.
- `complete`: finish the native goal without sending the close-pill completion event, then leave a visible `Waiting for next goal.` placeholder so the goal lane stays ready for the next objective.
- `park`, `wait`, `waiting`, or `next-goal`: set a visible `Waiting for next goal.` placeholder without claiming that a goal was completed.
- `clear`: clear the native goal.
- `compact`: start native context compaction for the current thread.
- `auto-compact`: start native context compaction only when the current thread has an active goal.
- `disable-auto-compact`: remove plugin-added automatic compaction config keys.

`setup`, `bootstrap`, `set`, and `resume` do not enable automatic compaction by default. Use backend `setup --auto-compact` or `bootstrap --auto-compact` only when the user explicitly wants Codex's native automatic compaction config.

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
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py park --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py clear --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py auto-compact --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py disable-auto-compact --workspace C:\Users\LENOVO\Desktop\iqoption
```

## Verification

After every operation, report whether the JSON output includes `_native_goal_backend: true`. Report `_app_server_transport` when it is present: `proxy` is live Desktop transport, `direct` is backend state transport. For `set`, include the native `objective`, `status`, `tokensUsed`, and `timeUsedSeconds` fields.

For `compact` and `auto-compact`, report whether `_native_compact_backend: true` and `compactStarted: true` are present. If `compactDeferred: true` is returned, report it as a graceful non-blocking result and continue the goal. If `compactStarted` is false for another reason, show the returned reason. Native compaction is a Codex turn and is safest at an idle checkpoint before continuing goal work.

When `complete` or `park` returns `waitingForNextGoal: true`, `pillPreserved: true`, and `completionEventSent: false`, treat the current visible placeholder as the user's next-goal parking state.

## Summary

Keep the response short. State whether the native backend was reached and what goal state is active.
