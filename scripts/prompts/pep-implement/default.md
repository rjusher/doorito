# PEP Implement Prompt

You are implementing PEP __PEP_NUM__ by executing the unchecked steps in the plan.

## Your Task

Work through the implementation steps sequentially, checking them off as completed.

1. **Read the PEP:**
   - `__PEP_DIR__/summary.md` — problem, solution, acceptance criteria
   - `__PEP_DIR__/plan.md` — implementation steps to execute
   - `__PEP_DIR__/journal.md` (if exists) — resume from "Left Off" section

2. **Read all context files** listed in the plan's "Context Files" section.

3. **Update status** to "Implementing" in `__PEP_DIR__/summary.md` (Status field) and in `PEPs/INDEX.md` (status column) if not already set.

4. **Work through unchecked implementation steps** sequentially:
   - For each step:
     1. Read the step's Files, Details, and Verify subsections
     2. Implement the changes described
     3. Run the verification command
     4. If verification passes, check off the step: `- [x]` in `__PEP_DIR__/plan.md`
     5. If verification fails, fix the issue and re-verify
   - Do not skip steps or work out of order unless explicitly stated

5. **Create or update `__PEP_DIR__/journal.md`** with:
   - Today's date and session number
   - Steps completed (with status: done / partial / blocked)
   - Decisions made and rationale
   - A "Left Off" section with:
     - Last completed step
     - Next step to work on
     - Any blockers
     - Uncommitted work (if any)

## Quality Expectations

- Follow all coding conventions from CLAUDE.md and `aikb/conventions.md`
- Run verification commands after each step — do not skip them
- Write clean, production-quality code
- Do not add features beyond what the plan specifies

## Constraints

- Do not skip steps or modify unrelated code
- Do not over-engineer — implement exactly what the plan describes
- If context window is filling up, stop cleanly: update the journal with progress and the "Left Off" section, then stop
- Do not run the "Final Verification" or "Completion" sections — those are for the finalize command
