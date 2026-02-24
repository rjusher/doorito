#!/usr/bin/env bash
# Archive older entries from IMPLEMENTED/LATEST.md when count exceeds 10.
# Moves entries beyond the newest 10 to PAST_YYYYMMDD.md.
# Usage: scripts/pep-archive.sh

set -euo pipefail

PEPS_DIR="$(cd "$(dirname "$0")/.." && pwd)/PEPs"
LATEST_FILE="$PEPS_DIR/IMPLEMENTED/LATEST.md"
TODAY=$(date +%Y%m%d)
PAST_FILE="$PEPS_DIR/IMPLEMENTED/PAST_${TODAY}.md"

if [ ! -f "$LATEST_FILE" ]; then
    echo "Error: $LATEST_FILE not found"
    exit 1
fi

# Count entries (lines starting with "### PEP")
ENTRY_COUNT=$(grep -c "^### PEP " "$LATEST_FILE" || true)

if [ "$ENTRY_COUNT" -le 10 ]; then
    echo "LATEST.md has $ENTRY_COUNT entries (limit: 10). No archival needed."
    exit 0
fi

ARCHIVE_COUNT=$((ENTRY_COUNT - 10))
echo "LATEST.md has $ENTRY_COUNT entries. Archiving $ARCHIVE_COUNT oldest entries..."

# Extract the header (everything before the first ### PEP entry)
HEADER_END=$(grep -n "^### PEP " "$LATEST_FILE" | head -1 | cut -d: -f1)
HEADER_END=$((HEADER_END - 1))

# Find the line number where the 11th entry starts (first entry to archive)
ENTRY_11_LINE=$(grep -n "^### PEP " "$LATEST_FILE" | sed -n '11p' | cut -d: -f1)

if [ -z "$ENTRY_11_LINE" ]; then
    echo "Error: Could not find the 11th entry to archive."
    exit 1
fi

# Find the line number of the "---" separator before the Past: link (or end of file)
SEPARATOR_LINE=$(grep -n "^---$" "$LATEST_FILE" | tail -1 | cut -d: -f1)
PAST_LINK_LINE=$(grep -n "^\*\*Past:\*\*" "$LATEST_FILE" | tail -1 | cut -d: -f1)

# The entries to archive are from ENTRY_11_LINE to just before the separator/past link
if [ -n "$SEPARATOR_LINE" ] && [ "$SEPARATOR_LINE" -gt "$ENTRY_11_LINE" ]; then
    ARCHIVE_END=$((SEPARATOR_LINE - 1))
else
    ARCHIVE_END=$(wc -l < "$LATEST_FILE")
fi

# Extract entries to archive
ARCHIVED_ENTRIES=$(sed -n "${ENTRY_11_LINE},${ARCHIVE_END}p" "$LATEST_FILE")

# Build the archive file
if [ -f "$PAST_FILE" ]; then
    # Append to existing archive for today
    echo "" >> "$PAST_FILE"
    echo "$ARCHIVED_ENTRIES" >> "$PAST_FILE"
    echo "Appended to existing $PAST_FILE"
else
    # Create new archive
    {
        echo "# Archived PEPs — $TODAY"
        echo ""
        echo "$ARCHIVED_ENTRIES"
    } > "$PAST_FILE"
    echo "Created $PAST_FILE"
fi

# Rebuild LATEST.md: header + first 10 entries + separator + updated Past link
{
    # Header
    sed -n "1,${HEADER_END}p" "$LATEST_FILE"

    # First 10 entries (from first entry to line before entry 11)
    FIRST_ENTRY_LINE=$((HEADER_END + 1))
    LAST_KEEP_LINE=$((ENTRY_11_LINE - 1))
    sed -n "${FIRST_ENTRY_LINE},${LAST_KEEP_LINE}p" "$LATEST_FILE"

    # Separator and past link
    echo "---"
    echo ""

    # Build past links from all PAST files
    printf "**Past:**"
    FIRST=true
    for past_file in $(ls -r "$PEPS_DIR"/IMPLEMENTED/PAST_*.md 2>/dev/null); do
        past_basename=$(basename "$past_file" .md)
        past_date=${past_basename#PAST_}
        # Extract PEP range from file
        first_pep=$(grep "^### PEP " "$past_file" | tail -1 | grep -oP 'PEP \K[0-9]+')
        last_pep=$(grep "^### PEP " "$past_file" | head -1 | grep -oP 'PEP \K[0-9]+')
        if $FIRST; then
            printf " [%s](%s)" "$past_date" "$(basename "$past_file")"
            FIRST=false
        else
            printf ", [%s](%s)" "$past_date" "$(basename "$past_file")"
        fi
        if [ -n "$first_pep" ] && [ -n "$last_pep" ]; then
            printf " (PEPs %s–%s)" "$first_pep" "$last_pep"
        fi
    done
    echo ""
} > "${LATEST_FILE}.tmp"

mv "${LATEST_FILE}.tmp" "$LATEST_FILE"

echo ""
echo "Archived $ARCHIVE_COUNT entries. LATEST.md now has 10 entries."
echo "Past file: IMPLEMENTED/PAST_${TODAY}.md"
