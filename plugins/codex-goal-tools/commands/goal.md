---
description: Best-effort local /goal command that calls Codex's native thread goal backend.
---

# /goal

Use this command only when the native Desktop `/goal` composer command is not available. This local plugin command intentionally mirrors the experimental `/goal` behavior by calling the real Codex `thread/goal/*` backend through:

```powershell
python C:\Users\LENOVO\.codex\local-marketplaces\goal-tools\plugins\codex-goal-tools\scripts\goal_backend.py
```

## Arguments

- No arguments, `show`, or `status`: show the current native goal.
- `set <objective>` or free-form objective text: set the native goal objective and ensure 200k auto-compaction is active.
- `pause`: pause the native goal.
- `resume`: resume the native goal and ensure 200k auto-compaction is active.
- `complete`: mark the native goal complete, then leave a paused `Waiting for next goal.` placeholder so the goal lane stays ready for the next objective.
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
5. For `compact` and `auto-compact`, confirm `_native_compact_backend: true` and `compactStarted: true` when compaction starts. If the remote compact task is temporarily rejected or times out, treat `compactDeferred: true` and `goalContinues: true` as a graceful non-blocking result.

Native context compaction is a Codex turn. It works best when invoked at an idle checkpoint before continuing a long-running goal; it cannot safely interrupt a currently active model turn. The plugin must not fail the goal just because compacting is deferred.

When `complete` returns `waitingForNextGoal: true`, treat the previous goal as genuinely completed and the current paused placeholder as a parking state for the user's next goal.

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
