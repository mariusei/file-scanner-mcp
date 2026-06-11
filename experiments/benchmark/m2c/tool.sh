#!/bin/bash
# M2b measurement by construction: all tool output is logged per episode
LOG=$1; shift
echo "=== CALL: $* ===" >> "$LOG"
"$@" 2>&1 | tee -a "$LOG"
