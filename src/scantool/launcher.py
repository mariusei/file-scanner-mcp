"""
FILE: launcher.py

PROBLEM:
  Registering scantool as an MCP server is the user's only install step, but
  the agent behind that client reads code through its shell. `sct` has to
  exist in that shell without a second step, on every platform, for every
  client — and the client may start the server from an ephemeral `uvx`
  environment whose console scripts are on no PATH.

SOLUTION:
  Two channels, both computed from the interpreter the server runs under:
  1. At server start, a launcher in uv's tool bin directory that runs
     `<this interpreter> -m scantool.cli`. A POSIX sh file (also for Git
     Bash/MSYS on Windows) and, on Windows, a .cmd file for cmd.exe and
     PowerShell. A marker comment makes it idempotent; a foreign `sct` is
     never touched.
  2. Every tool description carries the absolute fallback command line, for
     shells where the bin directory is not on PATH.

SCOPE:
  ✓ launcher files, marker, SCANTOOL_NO_CLI opt-out, never fails the server
  ✓ interpreter path in forward-slash, quoted form for descriptions
  ✗ never edits PATH or shell profiles; no symlinks (Windows needs privileges)
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__

log = logging.getLogger(__name__)

MARKER = "scantool-launcher"
OPT_OUT_ENV = "SCANTOOL_NO_CLI"


def interpreter() -> str:
    """The running interpreter, forward slashes on every platform.

    Not resolved: on POSIX a virtual environment's python is a symlink to
    the base interpreter, and following it would lose the environment that
    has scantool installed. Windows accepts forward slashes everywhere, and
    Git Bash mangles backslashes.
    """
    return sys.executable.replace("\\", "/")


def quoted_interpreter() -> str:
    return f'"{interpreter()}"'


def shell_hint(*examples: str) -> str:
    """One line for a tool description: the sct form(s) and the absolute fallback."""
    forms = " or ".join(f"`sct {example}`" for example in examples)
    return (
        f" In your shell: {forms} (if sct is not on PATH, "
        f"`{quoted_interpreter()} -m scantool.cli` replaces `sct`)."
    )


def shell_instructions() -> str:
    """The paragraph for the server-level instructions field."""
    return (
        "SHELL: the same reader is available in your shell as `sct` "
        "(`sct --help` lists the commands). If `sct` is not on PATH, run "
        f"`{quoted_interpreter()} -m scantool.cli` in its place."
    )


def launcher_dir() -> Path:
    """uv's tool bin directory; uv started us, so it is normally present."""
    uv = shutil.which("uv")
    if uv:
        try:
            result = subprocess.run(
                [uv, "tool", "dir", "--bin"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / ".local" / "bin"


def launcher_files(python: str = "", version: str = __version__) -> dict[str, bytes]:
    """Filename -> content. The sh file serves POSIX and Git Bash/MSYS; the
    .cmd file serves cmd.exe and PowerShell and only exists on Windows."""
    python = python or quoted_interpreter()
    files = {
        "sct": f'#!/bin/sh\n# {MARKER} {version}\nexec {python} -m scantool.cli "$@"\n'.encode(),
    }
    if os.name == "nt":
        cmd = f"@echo off\r\n:: {MARKER} {version}\r\n{python} -m scantool.cli %*\r\nexit /b %ERRORLEVEL%\r\n"
        files["sct.cmd"] = cmd.encode()
    return files


def ensure_launcher(bin_dir: Path | None = None) -> list[Path]:
    """Write the launcher(s) unless opted out; return the paths written.

    Never raises: a server must start even when the launcher cannot be
    written (read-only home, sandboxed client). Files without the marker
    belong to someone else and are left alone.
    """
    if os.environ.get(OPT_OUT_ENV, "") not in ("", "0"):
        return []
    written: list[Path] = []
    try:
        bin_dir = bin_dir if bin_dir is not None else launcher_dir()
        bin_dir.mkdir(parents=True, exist_ok=True)
        for name, content in launcher_files().items():
            target = bin_dir / name
            if target.exists():
                current = target.read_bytes()
                if MARKER.encode() not in current:
                    log.debug("%s exists and is not ours; left untouched", target)
                    continue
                if current == content:
                    continue
            target.write_bytes(content)
            target.chmod(0o755)
            written.append(target)
    except OSError as exc:
        log.debug("could not write the sct launcher: %s", exc)
    return written
