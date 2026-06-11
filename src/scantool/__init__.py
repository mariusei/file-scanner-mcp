"""File Scanner MCP - Beautiful file structure scanner with tree formatting."""

import os
import sys
from importlib.metadata import PackageNotFoundError, version

# === Windows/stdio buffering fix ===
# Prevents deadlocks when Claude Code sends parallel MCP requests over stdio.
# Without this, stdout buffering on Windows can cause responses to get stuck.
# See: https://github.com/jlowin/fastmcp/issues/1625
os.environ.setdefault('PYTHONUNBUFFERED', '1')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(write_through=True)  # type: ignore[union-attr]
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(write_through=True)  # type: ignore[union-attr]

# The version is owned by pyproject.toml; the metadata lookup keeps them from
# drifting apart (0.14 vs 0.15 happened with two hand-synced fields)
try:
    __version__ = version("scantool")
except PackageNotFoundError:
    __version__ = "0.0.0+uninstalled"

from .server import main

__all__ = ["main"]
