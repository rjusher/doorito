# PEP Review Prompt

You are reviewing inline suggestion notes for PEP __PEP_NUM__.

## Your Task

Scan all PEP files for `<!-- REVIEW: ... -->` markers, address each note, and remove resolved markers.

1. **Read all PEP files:**
   - `__PEP_DIR__/summary.md`
   - `__PEP_DIR__/plan.md`
   - `__PEP_DIR__/research.md` (if present)
   - `__PEP_DIR__/discussions.md` (if present)
   - `__PEP_DIR__/journal.md` (if present)

2. **Scan for `<!-- REVIEW: ... -->` markers** across all files.
   - If no markers are found, report that and stop.

3. **For each marker**, read the surrounding context and the note inside. Then:
   - **Understand the intent**: Is it a question, a steering suggestion, a correction, a request for investigation, or a decision?
   - **Act on it**: Depending on the note type:
     - **Question** → Research the answer using the codebase and aikb/ docs, then amend the file with the answer
     - **Steering suggestion** → Apply the suggested direction to the relevant section (rewrite text, adjust plan steps, update acceptance criteria, etc.)
     - **Correction** → Fix the indicated issue in place
     - **Investigation request** → Explore the codebase, then add findings to the relevant section or to `research.md`
     - **Decision** → Record the decision in `discussions.md` under "Design Decisions" with date, context, and rationale
     - **Ambiguous** → If you cannot confidently act on a note, leave it in place and flag it in your summary
   - **Remove the marker** after addressing it (delete the entire `<!-- REVIEW: ... -->` comment)

4. **Produce a summary** at the end of your work:
   - List each marker found, the file and context where it appeared, and what action you took
   - Flag any markers you left unresolved (with the reason)
   - Note any follow-up actions or side effects from addressing the notes

## Quality Expectations

- Amendments should be specific and grounded in the codebase, not generic
- When adjusting plan steps, preserve the existing format (Files, Details, Verify subsections)
- When adding to discussions.md, follow the template format (dated entries with context and rationale)
- Do not introduce unrelated changes — only modify what the review notes direct

## Constraints

- Only modify PEP files (`__PEP_DIR__/`) and `aikb/` docs if a note specifically directs it
- Do not modify source code unless a note explicitly requests it
- Do not remove markers you cannot confidently address — leave them for the next review pass
- If a note contradicts existing decisions in discussions.md, flag the conflict rather than silently overriding
