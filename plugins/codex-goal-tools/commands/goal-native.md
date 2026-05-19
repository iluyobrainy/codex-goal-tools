---
description: Set, view, pause, resume, complete, or clear the active native Codex thread goal.
---

# /goal-native

Bridge this slash command to Codex's native `thread/goal/*` app-server backend.

## Arguments

- No arguments, `show`, or `status`: show the current native goal.
- `set <objective>` or any other free-form text: set the native goal objective.
- `pause`: pause the native goal.
- `resume`: resume the native goal.
- `complete`: mark the native goal complete.
- `clear`: clear the native goal.
- `compact`: start native context compaction for the current thread.
- `auto-compact`: start native context compaction only when the current thread has an active goal.

`setup` and `bootstrap` enable Codex's native goals feature and add native auto-compaction defaults unless `--no-auto-compact` is used.

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

After every operation, report whether the JSON output includes `_native_goal_backend: true`. For `set`, include the native `objective`, `status`, `tokensUsed`, and `timeUsedSeconds` fields.

For `compact` and `auto-compact`, report whether `_native_compact_backend: true` and `compactStarted: true` are present. If `compactStarted` is false, show the returned reason. Native compaction is a Codex turn and is safest at an idle checkpoint before continuing goal work.

## Summary

Keep the response short. State whether the native backend was reached and what goal state is active.
