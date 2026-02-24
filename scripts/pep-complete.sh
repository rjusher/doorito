#!/usr/bin/env bash
# Validate that a PEP's completion checklist has been followed.
# Usage: scripts/pep-complete.sh <pep_number>
# Example: scripts/pep-complete.sh 0022

set -euo pipefail

PEPS_DIR="$(cd "$(dirname "$0")/.." && pwd)/PEPs"
INDEX_FILE="$PEPS_DIR/INDEX.md"
LATEST_FILE="$PEPS_DIR/IMPLEMENTED/LATEST.md"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <pep_number>"
    echo "  Example: $0 0022"
    exit 1
fi

PEP_NUM="$1"
# Zero-pad to 4 digits
PEP_NUM=$(printf "%04d" "$((10#$PEP_NUM))")

PASS=0
FAIL=0
WARN=0

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN + 1)); }

echo "Validating PEP $PEP_NUM completion..."
echo ""

# 1. Check if PEP directory still exists (should be deleted)
PEP_DIR=""
for dir in "$PEPS_DIR"/PEP_${PEP_NUM}_*/; do
    if [ -d "$dir" ]; then
        PEP_DIR="$dir"
        break
    fi
done

if [ -n "$PEP_DIR" ]; then
    fail "PEP directory still exists: $(basename "$PEP_DIR")/"
    echo "       Run: rm -rf $PEP_DIR"
else
    pass "PEP directory deleted"
fi

# 2. Check IMPLEMENTED/LATEST.md has an entry
if [ -f "$LATEST_FILE" ]; then
    if grep -q "### PEP $PEP_NUM:" "$LATEST_FILE"; then
        pass "Entry found in IMPLEMENTED/LATEST.md"

        # Check it has the required fields
        if grep -A3 "### PEP $PEP_NUM:" "$LATEST_FILE" | grep -q "Implemented"; then
            pass "LATEST.md entry has implementation date"
        else
            fail "LATEST.md entry missing implementation date"
        fi

        if grep -A3 "### PEP $PEP_NUM:" "$LATEST_FILE" | grep -q "Commit"; then
            pass "LATEST.md entry has commit hash(es)"
        else
            fail "LATEST.md entry missing commit hash(es)"
        fi

        if grep -A4 "### PEP $PEP_NUM:" "$LATEST_FILE" | grep -q "Summary"; then
            pass "LATEST.md entry has summary"
        else
            fail "LATEST.md entry missing summary"
        fi
    else
        fail "No entry for PEP $PEP_NUM in IMPLEMENTED/LATEST.md"
        echo "       Add an entry with implementation date, commit(s), and summary"
    fi
else
    fail "IMPLEMENTED/LATEST.md not found"
fi

# 3. Check INDEX.md does NOT have the PEP
if [ -f "$INDEX_FILE" ]; then
    if grep -qP "^\| $PEP_NUM " "$INDEX_FILE" || grep -qP "^\| 0*$((10#$PEP_NUM)) " "$INDEX_FILE"; then
        fail "PEP $PEP_NUM still listed in INDEX.md"
        echo "       Remove the row from INDEX.md"
    else
        pass "PEP $PEP_NUM removed from INDEX.md"
    fi
else
    fail "INDEX.md not found"
fi

# 4. Check LATEST.md entry count (warn if > 10)
if [ -f "$LATEST_FILE" ]; then
    ENTRY_COUNT=$(grep -c "^### PEP " "$LATEST_FILE" || true)
    if [ "$ENTRY_COUNT" -gt 10 ]; then
        warn "LATEST.md has $ENTRY_COUNT entries (max 10). Run: make pep-archive"
    else
        pass "LATEST.md has $ENTRY_COUNT entries (within limit)"
    fi
fi

# 5. Check that aikb/ files were likely updated (check git status for recent changes)
AIKB_CHANGED=$(git -C "$(dirname "$PEPS_DIR")" diff --name-only HEAD~3 HEAD -- aikb/ 2>/dev/null | wc -l || echo "0")
if [ "$AIKB_CHANGED" -gt 0 ]; then
    pass "aikb/ files were modified in recent commits ($AIKB_CHANGED files)"
else
    warn "No aikb/ files modified in last 3 commits — verify the aikb impact map was followed"
fi

# Summary
echo ""
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Fix the failures above before considering PEP $PEP_NUM complete."
    exit 1
else
    if [ "$WARN" -gt 0 ]; then
        echo ""
        echo "PEP $PEP_NUM completion looks good, but review the warnings."
    else
        echo ""
        echo "PEP $PEP_NUM completion validated successfully."
    fi
    exit 0
fi
