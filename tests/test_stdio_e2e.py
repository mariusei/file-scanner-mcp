"""The server as a client sees it: a separate process, JSON-RPC over stdio
pipes, in a real git repository.

Every other test calls the tool functions in-process, so a server that
hangs when run as a process — as scan_directory did on Windows through
0.19.6, while every release was green — never showed up. Each response
here has a hard wall-clock deadline; a hang fails instead of stalling CI.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

DEADLINE = 60.0  # per response; CI runners are slow, a hang is forever

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


class StdioServer:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-c", "from scantool import main; main()"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.lines: queue.Queue[bytes | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        while True:
            try:
                line = self.lines.get(timeout=DEADLINE)
            except queue.Empty:
                self.proc.kill()
                pytest.fail(f"no response to {method} within {DEADLINE}s")
            if line is None:
                pytest.fail(f"server exited before answering {method}")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") == self.next_id:
                assert "error" not in message, message["error"]
                return message["result"]

    def notify(self, method: str):
        self._send({"jsonrpc": "2.0", "method": method})

    def _send(self, message: dict):
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.proc.stdin.flush()

    def call(self, tool: str, **arguments) -> str:
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        assert not result.get("isError"), result
        return result["content"][0]["text"]

    def close(self):
        self.proc.kill()
        self.proc.wait(timeout=DEADLINE)


@pytest.fixture
def server():
    s = StdioServer()
    s.request(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    s.notify("notifications/initialized")
    yield s
    s.close()


def _git(cwd: Path, *args: str):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app.py").write_text(
        "def entry():\n    return helper()\n\n\ndef helper():\n    return 1\n"
    )
    (tmp_path / "README.md").write_text("# Sample\n\nText.\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_lists_tools(server):
    names = {t["name"] for t in server.request("tools/list")["tools"]}
    assert {"scan_directory", "scan_file", "preview_directory", "search_structures"} <= names


@requires_git
def test_scan_directory_answers_inside_a_git_repo(server, repo):
    out = server.call("scan_directory", directory=str(repo))
    assert "app.py" in out and "README.md" in out


@requires_git
def test_preview_directory_answers_inside_a_git_repo(server, repo):
    out = server.call("preview_directory", directory=str(repo))
    assert "app.py" in out


@requires_git
def test_scan_file_answers_inside_a_git_repo(server, repo):
    out = server.call("scan_file", file_path=str(repo / "app.py"))
    assert "entry" in out and "helper" in out


def test_scan_directory_answers_outside_git(server, tmp_path):
    (tmp_path / "a.py").write_text("def a():\n    return 1\n")
    out = server.call("scan_directory", directory=str(tmp_path))
    assert "a.py" in out
