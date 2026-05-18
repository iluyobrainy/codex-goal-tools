---
name: goal-native
description: Use when the user types /goal-native, asks for goal status, wants to set, pause, resume, complete, clear, or compact during the active Codex goal, or wants the native Codex thread goal backend exposed in Desktop without a mock.
metadata:
  short-description: Native Codex goal bridge
---

# Goal Native

This skill is a thin Desktop UI wrapper around Codex's native experimental thread goal backend. It must not store goals itself or emulate goal state.

## UI Sync Priority

When Codex Desktop exposes native goal tools in the current thread, use them for starting visible goals because they emit the live goal update event that makes the Desktop goal pill appear immediately.

- Use `get_goal` for status.
- Use `create_goal` for a new active goal when no goal exists.
- If the current goal is the visible `Waiting for next goal.` placeholder and the user gives the next objective, clear the placeholder through the bridge, then call `create_goal` for the new objective so the pill appears immediately.

Do not call native `update_goal` with `status: "complete"` for normal `/goal` completion. Desktop treats that event as permission to close the pill. Use the Python bridge `complete` action instead; it records the previous objective in the command output and immediately parks the thread at a visible `Waiting for next goal.` goal so the lane remains visible.

If a higher-priority active goal instruction requires calling native `update_goal` with `status: "complete"`, call it, then immediately reopen the lane before ending the turn. Use `create_goal` with objective `Waiting for next goal.` because it emits the live Desktop event that makes the pill appear. Do not pause this waiting placeholder; paused goals can be hidden by the Desktop UI. If `create_goal` is unavailable, run the bridge `park` action instead.

Use the Python bridge below for capabilities the exposed native tools do not currently provide: `setup`, `pause`, `resume`, `clear`, `compact`, `auto-compact`, `disable-auto-compact`, `install-pill-rule`, and completion-with-waiting-placeholder.

If the bridge reaches the backend but the UI text does not repaint immediately, treat the backend state as authoritative and continue; the key invariant is that completion must not send the native close-pill event.

## Backend

Resolve the plugin-bundled native bridge script relative to this `SKILL.md`:

```powershell
$skillDir = Split-Path -Parent "<absolute path to this SKILL.md>"
$script = Resolve-Path (Join-Path $skillDir "..\..\scripts\goal_backend.py")
python $script <action> --workspace "<current workspace path>"
```

Supported actions:

- `setup`: ensure `~/.codex/config.toml` contains `[features] goals = true`, install the global AGENTS.md goal-pill rule, then check the native backend when a thread is available. It does not add auto-compaction defaults unless `--auto-compact` is passed.
- `status`: show the current native goal.
- `set --goal "<objective>"`: set the current native goal objective without changing compaction settings.
- `pause`: pause the current native goal.
- `resume`: resume the current native goal without changing compaction settings.
- `complete`: finish the current goal without sending the close-pill completion event, then leave a visible `Waiting for next goal.` placeholder so the goal lane stays ready for the next objective.
- `park`, `wait`, `waiting`, or `next-goal`: set a visible `Waiting for next goal.` placeholder without claiming that a current goal was completed. Use this after native completion closes the pill only when `create_goal` is unavailable; otherwise create the waiting goal natively.
- `clear`: clear the current native goal.
- `compact`: start native context compaction for this thread.
- `auto-compact`: start native context compaction only when this thread has an active native goal.
- `disable-auto-compact`: remove plugin-added `model_auto_compact_token_limit` and `compact_prompt` keys from `~/.codex/config.toml`.
- `install-pill-rule` or `sync-pill-rule`: install or refresh the global `~/.codex/AGENTS.md` rule that tells future threads to reopen `Waiting for next goal.` after completing a real goal.
- `smoke-test`: temporarily set and verify a native goal, then restore the previous goal.

Setup accepts optional flags:

- `--auto-compact`: opt in to Codex's native automatic context compaction config.
- `--no-auto-compact`: compatibility flag; auto-compaction config is already off by default.
- `--auto-compact-token-limit <number>`: set the native auto-compaction threshold when `--auto-compact` is used. The default is `200000`.
- `--compact-prompt "<prompt>"`: set the prompt used by Codex when compacting context when `--auto-compact` is used.

Native context compaction is itself a Codex turn. Use `compact` or `auto-compact` only at a convenient idle checkpoint before continuing goal work; it cannot safely interrupt an already-running model turn.

If compacting returns `compactDeferred: true`, treat it as a graceful non-blocking result: the active goal is still valid, work can continue, and compaction can be retried later.

If completing or parking returns `waitingForNextGoal: true`, `pillPreserved: true`, and `completionEventSent: false`, treat the current visible placeholder as the user's next-goal parking state.

## Usage

Parse the user's text after `/goal-native` or `goal-native`:

- `setup` or `install`: run `setup`.
- Empty, `show`, or `status`: run `status`.
- `set <objective>` or any free-form goal text: run `set --goal "<objective>"`.
- `pause`, `resume`, `complete`, `park`, `wait`, `waiting`, `next-goal`, or `clear`: run the matching action.
- `compact`: run `compact`.
- `auto-compact`, `autocompact`, or `compact-if-goal`: run `auto-compact`.
- `disable-auto-compact` or `disable-autocompact`: run `disable-auto-compact`.
- `install-pill-rule` or `sync-pill-rule`: run `install-pill-rule`.
- `test` or `smoke-test`: run `smoke-test`.

After every action, report whether `_native_goal_backend` is `true`. Keep the response short and include the active objective/status when present.

Also report `_app_server_transport` when it is present. `proxy` means the bridge used the running Desktop app-server control socket for better UI sync; `direct` means it used a separate app-server process and may update the UI only after Desktop observes the backend state.

For `compact` and `auto-compact`, report whether `_native_compact_backend` is `true` and whether `compactStarted` is `true`. If `compactDeferred` is `true`, say compaction was deferred but the goal continues. If compaction is skipped or rejected for another reason, include the reason.
