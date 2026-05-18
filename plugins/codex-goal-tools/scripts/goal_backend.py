#!/usr/bin/env python3
"""Call Codex's native thread/goal app-server API from a local command."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_AUTO_COMPACT_TOKEN_LIMIT = 200_000
DEFAULT_COMPACT_PROMPT = (
    "Summarize this thread so the active goal can continue after context "
    "compaction. Preserve the current goal objective and status, completed "
    "work, remaining tasks, important files, commands, failures, decisions, "
    "and the next concrete action. After compaction, resume the active goal "
    "from the next concrete action without asking the user to restate context."
)
WAITING_FOR_NEXT_GOAL = "Waiting for next goal."
GLOBAL_GOAL_RULE_MARKER_START = "<!-- codex-goal-tools:goal-pill-rule:start -->"
GLOBAL_GOAL_RULE_MARKER_END = "<!-- codex-goal-tools:goal-pill-rule:end -->"
GLOBAL_GOAL_PILL_RULE = f"""{GLOBAL_GOAL_RULE_MARKER_START}
## Goal Pill Behavior

When working with Codex native goals, completing a real goal with `update_goal(status="complete")` can close the Codex Desktop goal pill. If a real goal is completed, immediately reopen the lane before ending the turn by calling `create_goal` with the objective `Waiting for next goal.`. Leave that placeholder active so the pill stays visible for the next objective. Do not mark the waiting placeholder complete.
{GLOBAL_GOAL_RULE_MARKER_END}"""


def resolve_codex_executable() -> str:
    override = os.environ.get("CODEX_CLI_PATH")
    if override:
        return str(Path(override).expanduser())

    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe")
    candidates.append(Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return "codex"


def default_codex_home() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser()
    return Path.home() / ".codex"


def default_app_server_control_socket() -> Path:
    return default_codex_home() / "app-server-control" / "app-server-control.sock"


def proxy_env_preference() -> str:
    value = os.environ.get("CODEX_GOAL_USE_PROXY", "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return "force-proxy"
    if value in {"0", "false", "no", "off"}:
        return "force-direct"
    return "auto"


def build_app_server_commands() -> list[tuple[str, list[str]]]:
    codex = resolve_codex_executable()
    direct = ("direct", [codex, "app-server", "--enable", "goals"])
    proxy = ("proxy", [codex, "app-server", "proxy", "--enable", "goals"])
    preference = proxy_env_preference()

    if preference == "force-proxy":
        return [proxy]
    if preference == "force-direct":
        return [direct]
    if default_app_server_control_socket().exists():
        return [proxy, direct]
    return [direct]


class AppServerClient:
    def __init__(self) -> None:
        self._next_id = 1
        self._stdout: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._stderr: "queue.Queue[str]" = queue.Queue()
        self._pending_commands = build_app_server_commands()
        self.transport = "unknown"
        self._process: subprocess.Popen[str]
        self._start_next_process()

    def _start_next_process(self) -> None:
        if not self._pending_commands:
            raise RuntimeError("No codex app-server command is available")
        self.transport, command = self._pending_commands.pop(0)
        self._stdout = queue.Queue()
        self._stderr = queue.Queue()
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _restart_after_proxy_failure(self) -> bool:
        if self.transport != "proxy":
            return False
        if not self._pending_commands:
            return False
        self.close()
        self._start_next_process()
        return True

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._stdout.put(json.loads(line))
            except json.JSONDecodeError:
                self._stderr.put(line)

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        for line in self._process.stderr:
            line = line.strip()
            if line:
                self._stderr.put(line)

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def request(self, method: str, params: Any = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params

        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

        deadline = time.time() + REQUEST_TIMEOUT_SECONDS
        while time.time() < deadline:
            try:
                message = self._stdout.get(timeout=0.25)
            except queue.Empty:
                if self._process.poll() is not None:
                    if self._restart_after_proxy_failure():
                        return self.request(method, params)
                    raise RuntimeError("codex app-server exited before responding")
                continue

            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], sort_keys=True))
            return message.get("result", {})

        raise TimeoutError(f"Timed out waiting for {method}")

    def notify(self, method: str, params: Any = None) -> None:
        payload: dict[str, Any] = {"method": method}
        if params is not None:
            payload["params"] = params
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()


def normalize_workspace(value: str | None) -> str:
    if value:
        return str(Path(value).expanduser().resolve())
    return str(Path.cwd().resolve())


def default_config_path() -> Path:
    return default_codex_home() / "config.toml"


def default_agents_path() -> Path:
    return default_codex_home() / "AGENTS.md"


def quote_toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def upsert_top_level_key(lines: list[str], key: str, value: str) -> tuple[list[str], bool]:
    output: list[str] = []
    replaced = False
    inserted = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        is_section = stripped.startswith("[") and stripped.endswith("]")

        if is_section and not replaced and not inserted:
            output.append(f"{key} = {value}")
            output.append("")
            inserted = True

        if not is_section and stripped.startswith(f"{key}") and "=" in stripped and not replaced:
            output.append(f"{key} = {value}")
            replaced = True
            continue

        output.append(line)

    if not replaced and not inserted:
        if output and output[-1].strip():
            output.append("")
        output.append(f"{key} = {value}")
        inserted = True

    return output, replaced or inserted


def ensure_goals_feature_enabled(
    config_path: str | None = None,
    *,
    auto_compact: bool = False,
    auto_compact_token_limit: int = DEFAULT_AUTO_COMPACT_TOKEN_LIMIT,
    compact_prompt: str | None = DEFAULT_COMPACT_PROMPT,
) -> dict[str, Any]:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    original = path.read_text(encoding="utf-8") if path.exists() else ""
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines()

    output: list[str] = []
    features_found = False
    in_features = False
    goals_found = False

    for line in lines:
        stripped = line.strip()
        is_section = stripped.startswith("[") and stripped.endswith("]")

        if is_section:
            if in_features and not goals_found:
                output.append("goals = true")
            in_features = stripped == "[features]"
            features_found = features_found or in_features
            goals_found = False
            output.append(line)
            continue

        if in_features and stripped.startswith("goals") and "=" in stripped:
            output.append("goals = true")
            goals_found = True
        else:
            output.append(line)

    if in_features and not goals_found:
        output.append("goals = true")

    if not features_found:
        if output and output[-1].strip():
            output.append("")
        output.extend(["[features]", "goals = true"])

    auto_compact_enabled = False
    if auto_compact:
        output, _ = upsert_top_level_key(
            output,
            "model_auto_compact_token_limit",
            str(auto_compact_token_limit),
        )
        if compact_prompt:
            output, _ = upsert_top_level_key(
                output,
                "compact_prompt",
                quote_toml_string(compact_prompt),
            )
        auto_compact_enabled = True

    updated = newline.join(output)
    if updated or not original:
        updated += newline

    changed = updated != original
    backup_path = None
    if changed:
        if path.exists():
            backup_path = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
            backup_path.write_text(original, encoding="utf-8")
        path.write_text(updated, encoding="utf-8")

    return {
        "configPath": str(path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "goalsEnabled": True,
        "autoCompactEnabled": auto_compact_enabled,
        "autoCompactTokenLimit": auto_compact_token_limit if auto_compact else None,
        "compactPromptConfigured": bool(compact_prompt) if auto_compact else False,
    }


def ensure_global_goal_pill_rule(agents_path: str | None = None) -> dict[str, Any]:
    path = Path(agents_path).expanduser() if agents_path else default_agents_path()
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    original = path.read_text(encoding="utf-8") if path.exists() else ""
    newline = "\r\n" if "\r\n" in original else "\n"
    rule = GLOBAL_GOAL_PILL_RULE.replace("\n", newline)

    legacy_rule = (
        "# Goal Pill Behavior\n\n"
        "When working with Codex native goals, completing a real goal with "
        "`update_goal(status=\"complete\")` can close the Codex Desktop goal pill. "
        "If a real goal is completed, immediately reopen the lane before ending "
        "the turn by calling `create_goal` with the objective `Waiting for next goal.`. "
        "Leave that placeholder active so the pill stays visible for the next objective. "
        "Do not mark the waiting placeholder complete."
    )
    normalized_original = original.replace("\r\n", "\n")
    bom = "\ufeff" if normalized_original.startswith("\ufeff") else ""
    normalized_body = normalized_original[len(bom) :] if bom else normalized_original
    if GLOBAL_GOAL_RULE_MARKER_START not in normalized_body and normalized_body.startswith(legacy_rule):
        original = (bom + normalized_body[len(legacy_rule) :].lstrip("\n")).replace("\n", newline)

    start = original.find(GLOBAL_GOAL_RULE_MARKER_START)
    end = original.find(GLOBAL_GOAL_RULE_MARKER_END)

    if start != -1 and end != -1 and end > start:
        end += len(GLOBAL_GOAL_RULE_MARKER_END)
        prefix = original[:start].rstrip()
        suffix = original[end:]
        updated = f"{prefix}{newline}{newline}{rule}{suffix}" if prefix else rule + suffix
    else:
        updated = original.rstrip()
        if updated:
            updated += newline + newline
        updated += rule + newline

    if updated and not updated.endswith(newline):
        updated += newline

    changed = updated != original
    backup_path = None
    if changed:
        if path.exists():
            backup_path = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
            backup_path.write_text(original, encoding="utf-8")
        path.write_text(updated, encoding="utf-8")

    return {
        "agentsPath": str(path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "globalGoalPillRuleInstalled": True,
    }


def remove_top_level_keys(lines: list[str], keys: set[str]) -> tuple[list[str], list[str]]:
    output: list[str] = []
    removed: list[str] = []
    in_top_level = True

    for line in lines:
        stripped = line.strip()
        is_section = stripped.startswith("[") and stripped.endswith("]")
        if is_section:
            in_top_level = False
            output.append(line)
            continue

        if in_top_level:
            key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
            if key in keys:
                removed.append(key)
                continue

        output.append(line)

    return output, removed


def disable_auto_compact_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    path = path.resolve()

    if not path.exists():
        return {
            "configPath": str(path),
            "changed": False,
            "removedKeys": [],
            "autoCompactEnabled": False,
            "reason": "Config file does not exist.",
        }

    original = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    output, removed = remove_top_level_keys(
        original.splitlines(),
        {"model_auto_compact_token_limit", "compact_prompt"},
    )
    updated = newline.join(output)
    if updated:
        updated += newline

    changed = updated != original
    backup_path = None
    if changed:
        backup_path = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
        backup_path.write_text(original, encoding="utf-8")
        path.write_text(updated, encoding="utf-8")

    return {
        "configPath": str(path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "removedKeys": sorted(set(removed)),
        "autoCompactEnabled": False,
    }


def infer_marketplace_file() -> Path:
    script_path = Path(__file__).resolve()
    marketplace_root = script_path.parents[3]
    marketplace_file = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    if not marketplace_file.exists():
        raise RuntimeError(f"Could not infer marketplace file from script path: {script_path}")
    return marketplace_file


def normalize_marketplace_path(value: str | None) -> str:
    if value:
        return str(Path(value).expanduser().resolve())
    return str(infer_marketplace_file())


def install_plugin(client: AppServerClient, marketplace_path: str | None = None) -> dict[str, Any]:
    marketplace_file = normalize_marketplace_path(marketplace_path)
    return client.request(
        "plugin/install",
        {
            "marketplacePath": marketplace_file,
            "pluginName": "codex-goal-tools",
        },
    )


def initialize(client: AppServerClient) -> None:
    client.request(
        "initialize",
        {
            "clientInfo": {
                "name": "goal-command",
                "title": "Goal Command",
                "version": "1.0.0",
            },
            "capabilities": {"experimentalApi": True},
        },
    )
    client.notify("initialized")


def infer_thread_id(client: AppServerClient, workspace: str) -> str:
    result = client.request(
        "thread/list",
        {
            "limit": 1,
            "sortKey": "updated_at",
            "sortDirection": "desc",
            "cwd": workspace,
            "useStateDbOnly": True,
        },
    )
    threads = result.get("data") or []
    if not threads:
        raise RuntimeError(f"No Codex thread found for workspace: {workspace}")
    return threads[0]["id"]


def with_thread_id(args: argparse.Namespace, client: AppServerClient) -> str:
    return args.thread_id or infer_thread_id(client, normalize_workspace(args.workspace))


def parse_backend_error(error: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(error)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_usage_limit_error(error: str) -> bool:
    payload = parse_backend_error(error) or {}
    message = str(payload.get("message") or error)
    code = str(payload.get("code") or payload.get("codex_error_info") or "")
    haystack = f"{code}\n{message}".lower()
    return "usage_limit_exceeded" in haystack or "usage limit" in haystack


def deferred_compaction_response(
    thread_id: str,
    error: str,
    *,
    loaded_thread_before_compact: bool = False,
) -> dict[str, Any]:
    payload = parse_backend_error(error)
    result: dict[str, Any] = {
        "ok": True,
        "threadId": thread_id,
        "compactStarted": False,
        "compactDeferred": True,
        "goalContinues": True,
        "reason": (
            "Remote context compaction could not start right now. "
            "The active goal remains valid and should continue; retry compaction later."
        ),
    }
    if loaded_thread_before_compact:
        result["loadedThreadBeforeCompact"] = True
    if payload:
        result["backendError"] = payload
    else:
        result["backendError"] = {"message": error}
    return result


def start_context_compaction(client: AppServerClient, thread_id: str) -> dict[str, Any]:
    try:
        result = client.request("thread/compact/start", {"threadId": thread_id})
        return {
            "ok": True,
            "threadId": thread_id,
            "compactStarted": True,
            "response": result,
        }
    except TimeoutError as exc:
        return deferred_compaction_response(thread_id, str(exc))
    except RuntimeError as exc:
        error = str(exc)
        if is_usage_limit_error(error):
            return deferred_compaction_response(thread_id, error)
        if "thread not found" not in error:
            raise

    client.request("thread/resume", {"threadId": thread_id})
    try:
        result = client.request("thread/compact/start", {"threadId": thread_id})
    except TimeoutError as exc:
        return deferred_compaction_response(
            thread_id,
            str(exc),
            loaded_thread_before_compact=True,
        )
    except RuntimeError as exc:
        error = str(exc)
        if is_usage_limit_error(error):
            return deferred_compaction_response(
                thread_id,
                error,
                loaded_thread_before_compact=True,
            )
        raise
    return {
        "ok": True,
        "threadId": thread_id,
        "compactStarted": True,
        "loadedThreadBeforeCompact": True,
        "response": result,
    }


def complete_goal_and_wait(client: AppServerClient, thread_id: str) -> dict[str, Any]:
    previous = client.request("thread/goal/get", {"threadId": thread_id}).get("goal")
    completed = dict(previous or {})
    if completed:
        completed["status"] = "complete"
        completed["completedAt"] = int(time.time())
    parked = park_waiting_goal(client, thread_id)
    return {
        **parked,
        "completed": True,
        "completedGoal": completed or previous,
    }


def park_waiting_goal(client: AppServerClient, thread_id: str) -> dict[str, Any]:
    waiting = client.request(
        "thread/goal/set",
        {
            "threadId": thread_id,
            "objective": WAITING_FOR_NEXT_GOAL,
            "status": "active",
        },
    )
    return {
        "ok": True,
        "threadId": thread_id,
        "parked": True,
        "completionEventSent": False,
        "pillPreserved": True,
        "visiblePlaceholder": True,
        "waitingForNextGoal": True,
        "goal": waiting.get("goal"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call Codex's native thread/goal backend through app-server."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", help="Workspace path used to infer the latest thread.")
    common.add_argument("--thread-id", help="Explicit Codex thread id.")
    common.add_argument("--config-path", help="Optional Codex config.toml path for setup.")
    common.add_argument("--agents-path", help="Optional AGENTS.md path for the global pill rule.")
    common.add_argument("--marketplace-path", help="Optional marketplace.json path for plugin install.")
    common.add_argument(
        "--no-auto-compact",
        action="store_true",
        help="Deprecated compatibility flag. Auto-compaction config is off by default.",
    )
    common.add_argument(
        "--auto-compact",
        action="store_true",
        help="Opt in to adding native Codex auto-compact defaults during setup/bootstrap.",
    )
    common.add_argument(
        "--auto-compact-token-limit",
        type=int,
        default=DEFAULT_AUTO_COMPACT_TOKEN_LIMIT,
        help="Token threshold for native Codex auto-compaction during setup/bootstrap.",
    )
    common.add_argument(
        "--compact-prompt",
        default=DEFAULT_COMPACT_PROMPT,
        help="Prompt Codex should use when compacting context.",
    )

    set_parser = subparsers.add_parser("set", parents=[common], help="Set native thread goal.")
    set_parser.add_argument("--goal", required=True, help="Goal objective.")
    set_parser.add_argument("--token-budget", type=int, default=None, help="Optional token budget.")

    for name in (
        "bootstrap",
        "install-plugin",
        "setup",
        "install-pill-rule",
        "sync-pill-rule",
        "disable-auto-compact",
        "disable-autocompact",
        "status",
        "show",
        "pause",
        "resume",
        "complete",
        "park",
        "wait",
        "waiting",
        "next-goal",
        "clear",
        "compact",
        "auto-compact",
        "autocompact",
        "compact-if-goal",
        "smoke-test",
    ):
        subparsers.add_parser(name, parents=[common], help=f"{name.title()} native thread goal.")

    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"bootstrap", "install-plugin"}:
        result: dict[str, Any] = {"ok": True}
        if args.command == "bootstrap":
            result["setup"] = ensure_goals_feature_enabled(
                args.config_path,
                auto_compact=args.auto_compact and not args.no_auto_compact,
                auto_compact_token_limit=args.auto_compact_token_limit,
                compact_prompt=args.compact_prompt,
            )
            result["globalGoalPillRule"] = ensure_global_goal_pill_rule(args.agents_path)

        client = AppServerClient()
        try:
            initialize(client)
            result["pluginInstall"] = install_plugin(client, args.marketplace_path)
            result["pluginId"] = "codex-goal-tools@codex-goal-tools"
            try:
                thread_id = with_thread_id(args, client)
                result["goalStatus"] = client.request("thread/goal/get", {"threadId": thread_id})
                result["_native_goal_backend"] = True
                result["_app_server_transport"] = client.transport
                result["_thread_id"] = thread_id
            except Exception as exc:
                result["_native_goal_backend"] = False
                result["nativeCheckWarning"] = str(exc)
                result["_app_server_transport"] = client.transport
            return result
        finally:
            client.close()

    if args.command == "setup":
        result: dict[str, Any] = {
            "ok": True,
            "setup": ensure_goals_feature_enabled(
                args.config_path,
                auto_compact=args.auto_compact and not args.no_auto_compact,
                auto_compact_token_limit=args.auto_compact_token_limit,
                compact_prompt=args.compact_prompt,
            ),
            "globalGoalPillRule": ensure_global_goal_pill_rule(args.agents_path),
        }
        try:
            client = AppServerClient()
            try:
                initialize(client)
                thread_id = with_thread_id(args, client)
                result["goalStatus"] = client.request("thread/goal/get", {"threadId": thread_id})
                result["_native_goal_backend"] = True
                result["_app_server_transport"] = client.transport
                result["_thread_id"] = thread_id
            finally:
                client.close()
        except Exception as exc:
            result["_native_goal_backend"] = False
            result["nativeCheckWarning"] = str(exc)
        return result

    if args.command in {"install-pill-rule", "sync-pill-rule"}:
        return {
            "ok": True,
            "globalGoalPillRule": ensure_global_goal_pill_rule(args.agents_path),
        }

    if args.command in {"disable-auto-compact", "disable-autocompact"}:
        return {
            "ok": True,
            "autoCompact": disable_auto_compact_config(args.config_path),
        }

    client = AppServerClient()
    try:
        initialize(client)
        thread_id = with_thread_id(args, client)

        if args.command == "set":
            params: dict[str, Any] = {
                "threadId": thread_id,
                "objective": args.goal,
                "status": "active",
            }
            if args.token_budget is not None:
                params["tokenBudget"] = args.token_budget
            result = client.request("thread/goal/set", params)
        elif args.command in {"status", "show"}:
            result = client.request("thread/goal/get", {"threadId": thread_id})
        elif args.command == "pause":
            result = client.request("thread/goal/set", {"threadId": thread_id, "status": "paused"})
        elif args.command == "resume":
            result = client.request("thread/goal/set", {"threadId": thread_id, "status": "active"})
        elif args.command == "complete":
            result = complete_goal_and_wait(client, thread_id)
        elif args.command in {"park", "wait", "waiting", "next-goal"}:
            result = park_waiting_goal(client, thread_id)
        elif args.command == "clear":
            result = client.request("thread/goal/clear", {"threadId": thread_id})
        elif args.command == "compact":
            result = start_context_compaction(client, thread_id)
            result["_native_compact_backend"] = True
        elif args.command in {"auto-compact", "autocompact", "compact-if-goal"}:
            goal = client.request("thread/goal/get", {"threadId": thread_id}).get("goal")
            if not goal or goal.get("status") != "active":
                result = {
                    "ok": True,
                    "threadId": thread_id,
                    "compactStarted": False,
                    "reason": "No active goal is running for this thread.",
                    "goal": goal,
                }
            else:
                result = start_context_compaction(client, thread_id)
                result["goal"] = goal
            result["_native_compact_backend"] = bool(
                result.get("compactStarted") or result.get("compactDeferred")
            )
        elif args.command == "smoke-test":
            previous = client.request("thread/goal/get", {"threadId": thread_id}).get("goal")
            probe = f"Goal backend smoke test {int(time.time())}"
            client.request(
                "thread/goal/set",
                {
                    "threadId": thread_id,
                    "objective": probe,
                    "status": "active",
                },
            )
            checked = client.request("thread/goal/get", {"threadId": thread_id}).get("goal")
            if not checked or checked.get("objective") != probe:
                raise RuntimeError("Smoke test failed: set goal was not returned by native backend")

            if previous:
                restore_params: dict[str, Any] = {
                    "threadId": thread_id,
                    "objective": previous.get("objective"),
                    "status": previous.get("status", "active"),
                }
                if previous.get("tokenBudget") is not None:
                    restore_params["tokenBudget"] = previous["tokenBudget"]
                restored = client.request("thread/goal/set", restore_params).get("goal")
            else:
                client.request("thread/goal/clear", {"threadId": thread_id})
                restored = None

            result = {
                "ok": True,
                "smokeTest": {
                    "setObjective": probe,
                    "verifiedObjective": checked.get("objective"),
                    "restoredPreviousGoal": previous is not None,
                    "restoredGoal": restored,
                },
            }
        else:
            raise RuntimeError(f"Unknown command: {args.command}")

        result["_native_goal_backend"] = True
        result["_app_server_transport"] = client.transport
        result["_thread_id"] = thread_id
        return result
    finally:
        client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
