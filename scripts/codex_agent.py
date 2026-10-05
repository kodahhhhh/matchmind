#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=14"]
# ///
"""Run long Codex agents on the shared local app-server daemon.

Threads live in the daemon (`codex app-server daemon`), not in this process, so they
show up in `codex agents` / `codex resume` and keep running if this client exits.
State per agent is kept in ~/.matchpulse-agents/<name>/ (thread id + event log).

    codex_agent.py start NAME --cwd DIR --model M --effort high --prompt-file F
    codex_agent.py send NAME --prompt "follow-up"  # new turn, same thread
    codex_agent.py wait NAME        # block until the current turn ends
    codex_agent.py status [NAME]
    codex_agent.py interrupt NAME

Add --detach to start/send to return as soon as the turn is queued.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Any

from websockets.sync.client import unix_connect

warnings.filterwarnings("ignore", message=r"connect\(\) must be used")

STATE_ROOT = Path.home() / ".matchpulse-agents"
SOCKET = Path.home() / ".codex/app-server-control/app-server-control.sock"


class AppServer:
    """JSON-RPC client for the daemon control socket (WebSocket over Unix)."""

    def __init__(self, log: Path | None = None) -> None:
        subprocess.run(
            ["codex", "app-server", "daemon", "start"], check=True, capture_output=True
        )
        self.ws = unix_connect(str(SOCKET), uri="ws://localhost/", max_size=None)
        self.next_id = 0
        self.log = log.open("a") if log else None
        self.request(
            "initialize",
            {"clientInfo": {"name": "matchpulse-orchestrator", "version": "1"}},
        )
        self.notify("initialized")

    def _send(self, msg: dict[str, Any]) -> None:
        self.ws.send(json.dumps(msg))

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"method": method, **({"params": params} if params else {})})

    def read(self) -> dict[str, Any]:
        msg = json.loads(self.ws.recv())
        if self.log and "method" in msg and not msg["method"].endswith("Delta"):
            self.log.write(json.dumps({"t": time.time(), **msg}) + "\n")
            self.log.flush()
        if "method" in msg and "id" in msg:  # server -> client request (approvals etc.)
            self._send({"id": msg["id"], "result": {"decision": "accept"}})
        return msg

    def request(self, method: str, params: dict[str, Any]) -> Any:
        self.next_id += 1
        rid = self.next_id
        self._send({"id": rid, "method": method, "params": params})
        while True:
            msg = self.read()
            if msg.get("id") == rid and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result")

    def wait_turn(self, thread_id: str) -> dict[str, Any]:
        """Block until a turn on thread_id completes; return the last agent message."""
        last_text = ""
        while True:
            msg = self.read()
            p = msg.get("params") or {}
            if p.get("threadId") not in (None, thread_id):
                continue
            m = msg.get("method")
            if (
                m == "item/completed"
                and (p.get("item") or {}).get("type") == "agentMessage"
            ):
                last_text = p["item"].get("text", "")
            elif m == "turn/completed":
                return {"turn": p.get("turn"), "last_message": last_text}
            elif m == "error":
                print(f"[error] {json.dumps(p)[:500]}", file=sys.stderr)

    def close(self) -> None:
        self.ws.close()


def state_dir(name: str) -> Path:
    d = STATE_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(name: str) -> dict[str, Any]:
    f = state_dir(name) / "state.json"
    if not f.exists():
        sys.exit(f"no agent named {name}")
    return json.loads(f.read_text())


def save_state(name: str, state: dict[str, Any]) -> None:
    (state_dir(name) / "state.json").write_text(json.dumps(state, indent=2))


def start_turn(srv: AppServer, state: dict[str, Any], text: str) -> None:
    srv.request(
        "turn/start",
        {
            "threadId": state["thread_id"],
            "input": [{"type": "text", "text": text}],
            "model": state["model"],
            "effort": state["effort"],
        },
    )


def finish(name: str, srv: AppServer, state: dict[str, Any]) -> None:
    result = srv.wait_turn(state["thread_id"])
    (state_dir(name) / "last_message.md").write_text(result["last_message"])
    status = (result["turn"] or {}).get("status")
    print(f"[{name}] turn finished: {status}\n\n{result['last_message']}")


def cmd_start(a: argparse.Namespace) -> None:
    prompt = Path(a.prompt_file).read_text() if a.prompt_file else a.prompt
    srv = AppServer(state_dir(a.name) / "events.jsonl")
    res = srv.request(
        "thread/start",
        {
            "cwd": str(Path(a.cwd).resolve()),
            "model": a.model,
            "approvalPolicy": "never",
            "sandbox": "danger-full-access",
        },
    )
    thread_id = res["thread"]["id"]
    try:
        srv.request("thread/name/set", {"threadId": thread_id, "name": a.name})
    except RuntimeError:
        pass
    state = {"thread_id": thread_id, "cwd": a.cwd, "model": a.model, "effort": a.effort}
    save_state(a.name, state)
    print(
        f"[{a.name}] thread {thread_id} on {a.model} ({a.effort}) in {a.cwd}",
        flush=True,
    )
    start_turn(srv, state, prompt)
    if a.detach:
        return
    finish(a.name, srv, state)


def resume(srv: AppServer, state: dict[str, Any]) -> None:
    srv.request("thread/resume", {"threadId": state["thread_id"]})


def cmd_send(a: argparse.Namespace) -> None:
    state = load_state(a.name)
    srv = AppServer(state_dir(a.name) / "events.jsonl")
    resume(srv, state)
    start_turn(
        srv, state, Path(a.prompt_file).read_text() if a.prompt_file else a.prompt
    )
    if not a.detach:
        finish(a.name, srv, state)


def cmd_wait(a: argparse.Namespace) -> None:
    state = load_state(a.name)
    srv = AppServer(state_dir(a.name) / "events.jsonl")
    res = srv.request("thread/resume", {"threadId": state["thread_id"]})
    status = (res.get("thread") or {}).get("status") or {}
    if status.get("type") != "active":
        print(f"[{a.name}] not running (status: {status})")
        return
    finish(a.name, srv, state)


def cmd_interrupt(a: argparse.Namespace) -> None:
    state = load_state(a.name)
    srv = AppServer()
    res = srv.request("thread/resume", {"threadId": state["thread_id"]})
    turns = (res.get("thread") or {}).get("turns") or []
    if turns:
        srv.request(
            "turn/interrupt",
            {"threadId": state["thread_id"], "turnId": turns[-1]["id"]},
        )
    print(f"[{a.name}] interrupted")


def cmd_status(a: argparse.Namespace) -> None:
    names = (
        [a.name]
        if a.name
        else sorted(p.name for p in STATE_ROOT.glob("*") if p.is_dir())
    )
    srv = AppServer()
    for n in names:
        st = load_state(n)
        res = srv.request("thread/read", {"threadId": st["thread_id"]})
        status = (res.get("thread") or {}).get("status")
        label = f"{st['model']} ({st['effort']})"
        print(f"{n:12} {label:22} {json.dumps(status)}  {st['cwd']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("start")
    s.add_argument("name")
    s.add_argument("--cwd", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--effort", default="high")
    s.add_argument("--prompt")
    s.add_argument("--prompt-file")
    s.add_argument("--detach", action="store_true")
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("send")
    s.add_argument("name")
    s.add_argument("--prompt")
    s.add_argument("--prompt-file")
    s.add_argument("--detach", action="store_true")
    s.set_defaults(fn=cmd_send)
    for name, fn in [("wait", cmd_wait), ("interrupt", cmd_interrupt)]:
        s = sub.add_parser(name)
        s.add_argument("name")
        s.set_defaults(fn=fn)
    s = sub.add_parser("status")
    s.add_argument("name", nargs="?")
    s.set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
