---
description: Best-effort local /goal command that calls Codex's native thread goal backend.
---

# /goal

Use this command only when the native Desktop `/goal` composer command is not available. This local plugin command intentionally mirrors the experimental `/goal` behavior by calling the real Codex `thread/goal/*` backend through:

```powershell
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py
```

## UI Sync Priority

If the current Codex thread exposes native goal tools, use them for starting visible goals because they update the Desktop goal pill immediately:

- `get_goal` for status.
- `create_goal` for a new active goal when there is no existing goal.
- If the current goal is the visible `Waiting for next goal.` placeholder and the user gives the next objective, clear the placeholder through the bridge, then call `create_goal` for the new objective.

Do not call native `update_goal` with `status: "complete"` for normal `/goal` completion. Desktop removes the pill when that event is sent. Use the Python bridge `complete` action instead; it records the finished objective in the command output and parks the thread at a visible `Waiting for next goal.` goal so the pill can remain visible.

If a higher-priority active goal instruction requires native `update_goal` with `status: "complete"`, immediately reopen the lane before ending the turn. Use native `create_goal` with objective `Waiting for next goal.` so Desktop shows the pill again. Do not pause this waiting placeholder; paused goals can be hidden by the Desktop UI. If `create_goal` is unavailable, run the bridge `park` action.

Use the Python bridge for `setup`, `pause`, `resume`, `clear`, `compact`, `auto-compact`, and completion-with-waiting-placeholder. The bridge will use the running Desktop app-server proxy when its control socket is available, otherwise it falls back to a direct app-server process.

## Arguments

- No arguments, `show`, or `status`: show the current native goal.
- `set <objective>` or free-form objective text: set the native goal objective and ensure 200k auto-compaction is active.
- `pause`: pause the native goal.
- `resume`: resume the native goal and ensure 200k auto-compaction is active.
- `complete`: finish the native goal without sending the close-pill completion event, then leave a visible `Waiting for next goal.` placeholder so the goal lane stays ready for the next objective.
- `park`, `wait`, `waiting`, or `next-goal`: set a visible `Waiting for next goal.` placeholder without claiming that a goal was completed.
- `clear`: clear the native goal.
- `compact`: start native context compaction for this thread.
- `auto-compact`: compact only when this thread has an active native goal.

`setup`, `bootstrap`, `set`, and `resume` also configure Codex's native auto-compaction defaults:

```toml
model_auto_compact_token_limit = 200000
compact_prompt = "Summarize this thread so the active goal can continue after context compaction..."
```

## Workflow

1. Parse the text after `/goal`.
2. Use the current workspace path for `--workspace`.
3. Run the matching `goal_backend.py` operation.
4. Confirm `_native_goal_backend: true` in the output.
5. Report `_app_server_transport` when present: `proxy` is live Desktop transport, `direct` is backend state transport.
6. For `compact` and `auto-compact`, confirm `_native_compact_backend: true` and `compactStarted: true` when compaction starts. If the remote compact task is temporarily rejected or times out, treat `compactDeferred: true` and `goalContinues: true` as a graceful non-blocking result.

Native context compaction is a Codex turn. It works best when invoked at an idle checkpoint before continuing a long-running goal; it cannot safely interrupt a currently active model turn. The plugin must not fail the goal just because compacting is deferred.

When `complete` or `park` returns `waitingForNextGoal: true`, `pillPreserved: true`, and `completionEventSent: false`, treat the current visible placeholder as the user's next-goal parking state.

## Verification

For testing, set a temporary goal, read it back, then clear it:

```powershell
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py set --workspace C:\Users\LENOVO\Desktop\iqoption --goal "Temporary native goal command test"
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py status --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py clear --workspace C:\Users\LENOVO\Desktop\iqoption
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py auto-compact --workspace C:\Users\LENOVO\Desktop\iqoption
```

## Summary

Keep the response short and make clear whether the plugin command reached the native backend.
