---
name: goal-native
description: Use when the user types /goal-native, asks for goal status, wants to set, pause, resume, complete, or clear the active Codex goal, or wants the native Codex thread goal backend exposed in Desktop without a mock.
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

- `setup`: ensure `~/.codex/config.toml` contains `[features] goals = true`, then check the native backend when a thread is available.
- `status`: show the current native goal.
- `set --goal "<objective>"`: set the current native goal objective.
- `pause`: pause the current native goal.
- `resume`: resume the current native goal.
- `complete`: mark the current native goal complete.
- `clear`: clear the current native goal.
- `smoke-test`: temporarily set and verify a native goal, then restore the previous goal.

## Usage

Parse the user's text after `/goal-native` or `goal-native`:

- `setup` or `install`: run `setup`.
- Empty, `show`, or `status`: run `status`.
- `set <objective>` or any free-form goal text: run `set --goal "<objective>"`.
- `pause`, `resume`, `complete`, or `clear`: run the matching action.
- `test` or `smoke-test`: run `smoke-test`.

After every action, report whether `_native_goal_backend` is `true`. Keep the response short and include the active objective/status when present.
