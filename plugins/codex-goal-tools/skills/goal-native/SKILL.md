---
name: goal-native
description: Use when the user types /goal-native, asks for goal status, wants to set, pause, resume, complete, clear, or compact during the active Codex goal, or wants the native Codex thread goal backend exposed in Desktop without a mock.
metadata:
  short-description: Native Codex goal bridge
---

# Goal Native

This skill is a thin Desktop UI wrapper around Codex's native experimental thread goal backend. It must not store goals itself or emulate goal state.

## Backend

Resolve the plugin-bundled native bridge script relative to this `SKILL.md`:

```powershell
$skillDir = Split-Path -Parent "<absolute path to this SKILL.md>"
$script = Resolve-Path (Join-Path $skillDir "..\..\scripts\goal_backend.py")
python $script <action> --workspace "<current workspace path>"
```

Supported actions:

- `setup`: ensure `~/.codex/config.toml` contains `[features] goals = true`, add native auto-compaction defaults, then check the native backend when a thread is available.
- `status`: show the current native goal.
- `set --goal "<objective>"`: set the current native goal objective and ensure 200k auto-compaction is active.
- `pause`: pause the current native goal.
- `resume`: resume the current native goal and ensure 200k auto-compaction is active.
- `complete`: mark the current native goal complete, then leave a paused `Waiting for next goal.` placeholder so the goal lane stays ready for the next objective.
- `clear`: clear the current native goal.
- `compact`: start native context compaction for this thread.
- `auto-compact`: start native context compaction only when this thread has an active native goal.
- `smoke-test`: temporarily set and verify a native goal, then restore the previous goal.

Setup accepts optional flags:

- `--no-auto-compact`: leave Codex auto-compaction config untouched.
- `--auto-compact-token-limit <number>`: set the native auto-compaction threshold. The default is `200000`.
- `--compact-prompt "<prompt>"`: set the prompt used by Codex when compacting context.

Native context compaction is itself a Codex turn. Use `compact` or `auto-compact` only at a convenient idle checkpoint before continuing goal work; it cannot safely interrupt an already-running model turn.

If compacting returns `compactDeferred: true`, treat it as a graceful non-blocking result: the active goal is still valid, work can continue, and compaction can be retried later.

If completing returns `waitingForNextGoal: true`, treat the previous goal as genuinely completed and the current paused placeholder as a parking state for the user's next goal.

## Usage

Parse the user's text after `/goal-native` or `goal-native`:

- `setup` or `install`: run `setup`.
- Empty, `show`, or `status`: run `status`.
- `set <objective>` or any free-form goal text: run `set --goal "<objective>"`.
- `pause`, `resume`, `complete`, or `clear`: run the matching action.
- `compact`: run `compact`.
- `auto-compact`, `autocompact`, or `compact-if-goal`: run `auto-compact`.
- `test` or `smoke-test`: run `smoke-test`.

After every action, report whether `_native_goal_backend` is `true`. Keep the response short and include the active objective/status when present.

For `compact` and `auto-compact`, report whether `_native_compact_backend` is `true` and whether `compactStarted` is `true`. If `compactDeferred` is `true`, say compaction was deferred but the goal continues. If compaction is skipped or rejected for another reason, include the reason.
