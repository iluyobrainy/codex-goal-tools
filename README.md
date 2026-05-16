# Codex Goal Tools

Expose Codex's native experimental thread goal backend in Codex Desktop through a bundled plugin skill.

This is not a fake goal store. The `goal-native` skill calls Codex's native `thread/goal/*` app-server API.

Version `0.3.0` also adds goal-aware context compaction support. Setup configures Codex's native auto-compaction threshold at `200000` tokens, and `set`/`resume` keep that config active automatically. If the remote compact task is temporarily rejected or times out, the plugin now returns a graceful `compactDeferred` result so the active goal can keep running and retry compaction later.

## Install From Codex Desktop

Open Plugins, choose **Add marketplace**, then enter:

```text
Source: iluyobrainy/codex-goal-tools
Git ref: main
Sparse paths: leave empty
```

After adding the marketplace, install/enable **Codex Goal Tools** from the plugin list. Restart Codex Desktop if the skill does not appear immediately.

## One-Command Install

If you want marketplace add, plugin install/enable, and goal setup in one step:

```powershell
irm https://raw.githubusercontent.com/iluyobrainy/codex-goal-tools/main/install.ps1 | iex
```

For a safer review-first install, download/read `install.ps1` first, then run it.

## Install From CLI

```powershell
codex plugin marketplace add iluyobrainy/codex-goal-tools
```

Then install/enable **Codex Goal Tools** from the plugin list, or run `install.ps1`.

## First Run

In a Codex thread, run:

```text
$goal-native setup
```

This safely ensures `~/.codex/config.toml` contains:

```toml
[features]
goals = true
```

It also adds native auto-compaction defaults:

```toml
model_auto_compact_token_limit = 200000
compact_prompt = "Summarize this thread so the active goal can continue after context compaction..."
```

`set` and `resume` also verify those defaults, so normal goal usage keeps auto-compaction active.

Use `--no-auto-compact` with the backend script if you want setup to leave those config keys untouched.

If setup changes an existing config file, it creates a timestamped `.bak` backup first.

Then test:

```text
$goal-native status
```

Expected:

```text
_native_goal_backend: true
```

## Direct Smoke Test

From a workspace that has an existing Codex thread:

```powershell
python ".\plugins\codex-goal-tools\scripts\goal_backend.py" smoke-test --workspace "C:\path\to\your\workspace"
```

Expected:

```json
{
  "ok": true,
  "_native_goal_backend": true
}
```

## Commands

- `setup`: enable the native goals feature in `config.toml` and verify backend access when possible.
- `bootstrap`: install/enable the plugin, enable native goals in `config.toml`, and verify backend access when possible.
- `install-plugin`: install/enable the plugin from its marketplace.
- `status`: show the current thread goal.
- `set <objective>`: set the active native goal and ensure 200k auto-compaction is configured.
- `pause`: pause the active goal.
- `resume`: resume the active goal and ensure 200k auto-compaction is configured.
- `complete`: mark the goal complete.
- `clear`: clear the goal.
- `compact`: start native context compaction for the thread.
- `auto-compact`: start native context compaction only when the thread has an active goal.
- `smoke-test`: temporarily set/verify a goal, then restore the previous goal.

Native context compaction is itself a Codex turn. It is safest at a quiet checkpoint before continuing a goal; it cannot interrupt an already-running model turn from inside that same turn.

## Auto-Compact Usage

After install or update, run:

```text
$goal-native setup
```

Then, before continuing a long goal when the context is getting heavy, run:

```text
$goal-native auto-compact
```

The command reports `_native_compact_backend: true` and `compactStarted: true` when Codex accepts the compaction request. If Codex cannot start the remote compact task right then, the command returns `compactDeferred: true`, `goalContinues: true`, and exits cleanly so the goal can continue.

## Notes

The native `/goal` feature is experimental in Codex. This plugin is a convenience bridge for Codex Desktop while native UI exposure is still evolving.
