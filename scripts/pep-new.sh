#!/usr/bin/env bash
# Create a new PEP directory from the template with the next available number.
# Usage: scripts/pep-new.sh <title>
# Example: scripts/pep-new.sh store_billing
#          scripts/pep-new.sh "multi platform sync"  (spaces converted to underscores)

set -euo pipefail

PEPS_DIR="$(cd "$(dirname "$0")/.." && pwd)/PEPs"
TEMPLATE_DIR="$PEPS_DIR/PEP_0000_template"
INDEX_FILE="$PEPS_DIR/INDEX.md"
TODAY=$(date +%Y-%m-%d)

if [ $# -lt 1 ]; then
    echo "Usage: $0 <title>"
    echo "  Example: $0 store_billing"
    echo "  Example: $0 \"multi platform sync\""
    exit 1
fi

# Normalize title: lowercase, spaces to underscores, strip non-alphanumeric except underscores
TITLE=$(echo "$*" | tr '[:upper:]' '[:lower:]' | tr ' ' '_' | tr -cd 'a-z0-9_')

if [ -z "$TITLE" ]; then
    echo "Error: Title cannot be empty after normalization."
    exit 1
fi

# Find the next available PEP number by scanning existing directories and INDEX.md
NEXT_NUM=0
for dir in "$PEPS_DIR"/PEP_[0-9][0-9][0-9][0-9]_*/; do
    if [ -d "$dir" ]; then
        num=$(basename "$dir" | grep -oP 'PEP_\K[0-9]+')
        num=$((10#$num))  # Remove leading zeros
        if [ "$num" -ge "$NEXT_NUM" ]; then
            NEXT_NUM=$((num + 1))
        fi
    fi
done

# Also check IMPLEMENTED/LATEST.md and any PAST files for used numbers
for impl_file in "$PEPS_DIR"/IMPLEMENTED/*.md; do
    if [ -f "$impl_file" ]; then
        while IFS= read -r line; do
            if [[ "$line" =~ ^###[[:space:]]PEP[[:space:]]([0-9]+): ]]; then
                num=$((10#${BASH_REMATCH[1]}))
                if [ "$num" -ge "$NEXT_NUM" ]; then
                    NEXT_NUM=$((num + 1))
                fi
            fi
        done < "$impl_file"
    fi
done

PADDED_NUM=$(printf "%04d" "$NEXT_NUM")
PEP_DIR="$PEPS_DIR/PEP_${PADDED_NUM}_${TITLE}"

if [ -d "$PEP_DIR" ]; then
    echo "Error: Directory already exists: $PEP_DIR"
    exit 1
fi

# Create PEP directory and copy templates
mkdir -p "$PEP_DIR"

# Only copy the 2 required files (summary.md + plan.md)
# Optional files (discussions.md, journal.md) are created manually when needed
for template_file in summary.md plan.md; do
    if [ -f "$TEMPLATE_DIR/$template_file" ]; then
        sed -e "s/NNNN/$PADDED_NUM/g" \
            -e "s/YYYY-MM-DD/$TODAY/g" \
            -e "s/Title of the Enhancement/${TITLE//_/ }/g" \
            -e "s/Author Name/Doorito Team/g" \
            "$TEMPLATE_DIR/$template_file" > "$PEP_DIR/$template_file"
    fi
done

# Format title for display (capitalize words)
DISPLAY_TITLE=$(echo "${TITLE//_/ }" | sed 's/\b\(.\)/\u\1/g')

echo "Created PEP $PADDED_NUM: $DISPLAY_TITLE"
echo "  Directory: PEPs/PEP_${PADDED_NUM}_${TITLE}/"
echo "  Files:     summary.md, plan.md (required)"
echo ""
echo "Next steps:"
echo "  1. Fill in the summary (problem, solution, acceptance criteria, risk)"
echo "  2. Optionally add research.md (copy from PEP_0000_template/) for codebase investigation before planning"
echo "  3. Fill in the plan (context files, steps with verification, aikb impact map)"
echo "  4. Optionally add discussions.md (copy from PEP_0000_template/) if design decisions needed"
echo "  5. Set status to Proposed when ready"
echo "  6. Add a row to PEPs/INDEX.md:"
echo "     | $PADDED_NUM | $DISPLAY_TITLE | Proposed | M | Low | — |"
