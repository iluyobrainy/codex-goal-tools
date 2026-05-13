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


class AppServerClient:
    def __init__(self) -> None:
        self._next_id = 1
        self._stdout: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._stderr: "queue.Queue[str]" = queue.Queue()
        self._process = subprocess.Popen(
            ["codex", "app-server", "--enable", "goals"],
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
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "config.toml"
    return Path.home() / ".codex" / "config.toml"


def ensure_goals_feature_enabled(config_path: str | None = None) -> dict[str, Any]:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call Codex's native thread/goal backend through app-server."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", help="Workspace path used to infer the latest thread.")
    common.add_argument("--thread-id", help="Explicit Codex thread id.")
    common.add_argument("--config-path", help="Optional Codex config.toml path for setup.")
    common.add_argument("--marketplace-path", help="Optional marketplace.json path for plugin install.")

    set_parser = subparsers.add_parser("set", parents=[common], help="Set native thread goal.")
    set_parser.add_argument("--goal", required=True, help="Goal objective.")
    set_parser.add_argument("--token-budget", type=int, default=None, help="Optional token budget.")

    for name in (
        "bootstrap",
        "install-plugin",
        "setup",
        "status",
        "show",
        "pause",
        "resume",
        "complete",
        "clear",
        "smoke-test",
    ):
        subparsers.add_parser(name, parents=[common], help=f"{name.title()} native thread goal.")

    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"bootstrap", "install-plugin"}:
        result: dict[str, Any] = {"ok": True}
        if args.command == "bootstrap":
            result["setup"] = ensure_goals_feature_enabled(args.config_path)

        client = AppServerClient()
        try:
            initialize(client)
            result["pluginInstall"] = install_plugin(client, args.marketplace_path)
            result["pluginId"] = "codex-goal-tools@codex-goal-tools"
            try:
                thread_id = with_thread_id(args, client)
                result["goalStatus"] = client.request("thread/goal/get", {"threadId": thread_id})
                result["_native_goal_backend"] = True
                result["_thread_id"] = thread_id
            except Exception as exc:
                result["_native_goal_backend"] = False
                result["nativeCheckWarning"] = str(exc)
            return result
        finally:
            client.close()

    if args.command == "setup":
        result: dict[str, Any] = {
            "ok": True,
            "setup": ensure_goals_feature_enabled(args.config_path),
        }
        try:
            client = AppServerClient()
            try:
                initialize(client)
                thread_id = with_thread_id(args, client)
                result["goalStatus"] = client.request("thread/goal/get", {"threadId": thread_id})
                result["_native_goal_backend"] = True
                result["_thread_id"] = thread_id
            finally:
                client.close()
        except Exception as exc:
            result["_native_goal_backend"] = False
            result["nativeCheckWarning"] = str(exc)
        return result

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
            result = client.request("thread/goal/set", {"threadId": thread_id, "status": "complete"})
        elif args.command == "clear":
            result = client.request("thread/goal/clear", {"threadId": thread_id})
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
