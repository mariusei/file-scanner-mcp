#!/bin/bash
# M2b-måling ved konstruksjon: all verktøyoutput logges per episode
LOG=$1; shift
echo "=== CALL: $* ===" >> "$LOG"
"$@" 2>&1 | tee -a "$LOG"
