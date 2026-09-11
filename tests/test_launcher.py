"""The `sct` launcher the server writes at startup, and the fallback command
line the tool descriptions carry.

The launcher is the only channel that reaches the agent's shell without a
user step, so it is exercised the way a shell would: the sh file through
its shebang (Git Bash on Windows), the .cmd file through cmd.exe, from a
directory with a space in its path and a PATH that does not contain uv.
"""

import asyncio
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scantool import launcher, server

EM_DASH_UTF8 = "—".encode()  # first line of the help text; cp1252 would give b"\x97"
CLIENTS = ("Claude", "Codex", "Cursor", "Copilot", "Cline", "Windsurf", "Gemini", "Zed")


def _git_bash() -> str | None:
    # GitHub's Windows runners carry Git for Windows; System32\bash.exe is
    # the WSL stub and must not be picked up.
    for candidate in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if candidate and Path(candidate).exists() and "System32" not in candidate:
            return candidate
    return None


def test_interpreter_is_quoted_with_forward_slashes():
    assert "\\" not in launcher.interpreter()
    quoted = launcher.quoted_interpreter()
    assert quoted.startswith('"') and quoted.endswith('"')
    assert Path(sys.executable).samefile(Path(launcher.interpreter()))


def test_launcher_files_carry_marker_interpreter_and_line_endings():
    files = launcher.launcher_files()
    sh = files["sct"].decode()
    assert sh.startswith("#!/bin/sh\n")
    assert f"# {launcher.MARKER} " in sh
    assert launcher.quoted_interpreter() in sh
    assert "\r" not in sh
    if os.name == "nt":
        cmd = files["sct.cmd"].decode()
        assert cmd.startswith("@echo off\r\n")
        assert f":: {launcher.MARKER} " in cmd
        assert launcher.quoted_interpreter() in cmd
        assert "\n" not in cmd.replace("\r\n", "")
    else:
        assert set(files) == {"sct"}


def test_writes_all_launchers_and_is_idempotent(tmp_path):
    bin_dir = tmp_path / "tool bin"
    written = launcher.ensure_launcher(bin_dir)
    assert {p.name for p in written} == set(launcher.launcher_files())
    if os.name != "nt":
        assert (bin_dir / "sct").stat().st_mode & stat.S_IXUSR
    assert launcher.ensure_launcher(bin_dir) == []


def test_foreign_sct_is_never_touched(tmp_path):
    foreign = b"#!/bin/sh\necho someone else's sct\n"
    (tmp_path / "sct").write_bytes(foreign)
    launcher.ensure_launcher(tmp_path)
    assert (tmp_path / "sct").read_bytes() == foreign


def test_stale_marked_launcher_is_rewritten(tmp_path):
    stale = f'#!/bin/sh\n# {launcher.MARKER} 0.0.1\nexec /old/python -m scantool.cli "$@"\n'
    (tmp_path / "sct").write_bytes(stale.encode())
    written = launcher.ensure_launcher(tmp_path)
    assert [p.name for p in written][:1] == ["sct"]
    assert (tmp_path / "sct").read_bytes() == launcher.launcher_files()["sct"]


def test_opt_out_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv(launcher.OPT_OUT_ENV, "1")
    assert launcher.ensure_launcher(tmp_path) == []
    assert not (tmp_path / "sct").exists()


def test_unwritable_bin_dir_never_raises(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    assert launcher.ensure_launcher(blocker / "bin") == []


def _path_without_uv(bin_dir: Path) -> str:
    """A PATH with the launcher's directory and the system, nothing from uv."""
    system = [p for p in os.environ.get("PATH", "").split(os.pathsep) if "uv" not in p.lower()]
    return os.pathsep.join([str(bin_dir), *system])


def _assert_help(raw: bytes) -> None:
    assert raw.startswith("sct —".encode()), raw[:80]
    assert EM_DASH_UTF8 in raw
    assert b"\r\n" not in raw


@pytest.mark.skipif(os.name == "nt" and _git_bash() is None, reason="no Git Bash on this runner")
def test_sh_launcher_runs_help_through_the_shell(tmp_path):
    bin_dir = tmp_path / "tool bin"
    launcher.ensure_launcher(bin_dir)
    env = {**os.environ, "PATH": _path_without_uv(bin_dir)}
    if os.name == "nt":
        command = [_git_bash(), "-c", "sct --help"]
    else:
        command = [str(bin_dir / "sct"), "--help"]
    result = subprocess.run(command, capture_output=True, env=env, timeout=120)
    assert result.returncode == 0, result.stderr
    _assert_help(result.stdout)


@pytest.mark.skipif(os.name != "nt", reason="cmd.exe launcher")
def test_cmd_launcher_runs_help_through_cmd(tmp_path):
    bin_dir = tmp_path / "tool bin"
    launcher.ensure_launcher(bin_dir)
    env = {**os.environ, "PATH": _path_without_uv(bin_dir)}
    for command in (["cmd", "/c", "sct.cmd", "--help"], ["cmd", "/c", "sct", "--help"]):
        result = subprocess.run(command, capture_output=True, env=env, cwd=tmp_path, timeout=120)
        assert result.returncode == 0, (command, result.stderr)
        _assert_help(result.stdout)
    result = subprocess.run(["cmd", "/c", "sct", "scan", "no-such-file"], env=env, timeout=120)
    assert result.returncode == 1


def test_every_tool_description_carries_the_absolute_fallback():
    fallback = f"`{launcher.quoted_interpreter()} -m scantool.cli` replaces `sct`"
    for tool in asyncio.run(server.mcp.list_tools()):
        assert fallback in (tool.description or ""), tool.name
        assert "`sct " in tool.description
    assert launcher.quoted_interpreter() in (server.mcp.instructions or "")


def test_nothing_names_a_client():
    sources = [
        Path(launcher.__file__).read_text(encoding="utf-8"),
        Path(server.__file__).parent.joinpath("cli.py").read_text(encoding="utf-8"),
        server.mcp.instructions or "",
        *(t.description or "" for t in asyncio.run(server.mcp.list_tools())),
    ]
    for text in sources:
        assert not any(client in text for client in CLIENTS), text[:120]
