# Codex Goal Tools

Expose Codex's native experimental thread goal backend in Codex Desktop through a bundled plugin skill.

This is not a fake goal store. The `goal-native` skill calls Codex's native `thread/goal/*` app-server API.

Version `0.3.0` also adds goal-aware context compaction support, but automatic compaction is no longer enabled by default. Normal `set` and `resume` calls use Codex's native `thread/goal/*` backend only. Run `compact` or `auto-compact` explicitly at an idle checkpoint when you want compaction, or opt in to native automatic compaction with `setup --auto-compact`. If the remote compact task is temporarily rejected or times out, the plugin returns a graceful `compactDeferred` result so the active goal can keep running and retry compaction later.

The skill uses Codex Desktop's in-thread native goal tools to start new visible goals, because those emit the live event that makes the native goal pill appear immediately. For completion, the bridge intentionally avoids the native close-pill completion event and parks the thread at a visible `Waiting for next goal.` state instead. When Desktop exposes its app-server control socket, the bridge uses the `proxy` transport for better UI sync; otherwise it falls back to direct backend state access.

If the native goal path has already closed the pill, reopen it by creating a new native goal named `Waiting for next goal.` and leave it active. This emits the live Desktop event that makes the pill visible again. Do not pause the waiting placeholder, because paused goals can be hidden by the Desktop UI. If native goal creation is unavailable, use `park` as the backend fallback.

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

It does not add native auto-compaction defaults. That keeps `/goal` close to the old native `thread/goal` behavior and avoids remote compaction failures interrupting normal goal work.

If you previously installed a version that added auto-compaction keys, run:

```text
$goal-native disable-auto-compact
```

To opt in to Codex's native automatic compaction config, run the backend script with `setup --auto-compact` or `bootstrap --auto-compact`.

If setup changes an existing config file, it creates a timestamped `.bak` backup first.

Then test:

```text
$goal-native status
```

Expected:

```text
_native_goal_backend: true
```

When using the Python bridge, `_app_server_transport` may also be shown:

```text
_app_server_transport: proxy
```

`proxy` means the bridge is connected through the running Desktop app-server. `direct` means the backend state was updated through a separate app-server process, so the Desktop pill may repaint after the next idle/turn boundary.

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
- `set <objective>`: set the active native goal without changing compaction settings.
- `pause`: pause the active goal.
- `resume`: resume the active goal without changing compaction settings.
- `complete`: finish the current goal without sending the close-pill completion event, then park visibly at `Waiting for next goal.`.
- `park`: set a visible `Waiting for next goal.` placeholder without claiming that a goal was completed.
- `clear`: clear the goal.
- `compact`: start native context compaction for the thread.
- `auto-compact`: start native context compaction only when the thread has an active goal.
- `disable-auto-compact`: remove plugin-added automatic compaction config keys.
- `smoke-test`: temporarily set/verify a goal, then restore the previous goal.

Native context compaction is itself a Codex turn. It is safest at a quiet checkpoint before continuing a goal; it cannot interrupt an already-running model turn from inside that same turn.

## Auto-Compact Usage

Before continuing a long goal when the context is getting heavy and the thread is idle, run:

```text
$goal-native auto-compact
```

The command reports `_native_compact_backend: true` and `compactStarted: true` when Codex accepts the compaction request. If Codex cannot start the remote compact task right then, the command returns `compactDeferred: true`, `goalContinues: true`, and exits cleanly so the goal can continue.

To opt in to automatic compaction config:

```text
$goal-native setup --auto-compact
```

## Notes

The native `/goal` feature is experimental in Codex. This plugin is a convenience bridge for Codex Desktop while native UI exposure is still evolving.
