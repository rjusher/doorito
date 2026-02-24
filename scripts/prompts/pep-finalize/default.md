# PEP Finalize Prompt

You are completing the post-implementation checklist for PEP __PEP_NUM__.

## Your Task

Run final verification, update documentation, and close out the PEP.

1. **Read the PEP:**
   - `__PEP_DIR__/plan.md` — specifically the "aikb Impact Map", "Final Verification", and "Completion" sections
   - `__PEP_DIR__/summary.md` — acceptance criteria

2. **Pre-check: verify all implementation steps are complete.**
   - Scan the "Implementation Steps" section of `plan.md`
   - Every step must be checked off: `- [x]`
   - If any steps are unchecked, **stop and report** which steps remain — do not proceed with finalization

3. **Execute the aikb Impact Map:**
   - For each entry in the map, update the listed `aikb/*.md` file with the described changes
   - Even entries marked "N/A" — verify the N/A is correct given the implementation
   - Check off each entry as completed

4. **Update `CLAUDE.md`** if the implementation changed:
   - Architecture or app structure
   - Development commands
   - Key dependencies
   - Coding conventions
   - Feature roadmap

5. **Run Final Verification** from the plan:
   - Execute each acceptance criteria check
   - Run integration checks
   - Run regression checks: `python manage.py check`, `ruff check .`
   - Report any failures

6. **Execute the Completion checklist:**
   - Add entry to `PEPs/IMPLEMENTED/LATEST.md` with:
     - PEP number and title
     - Implementation date (today)
     - Git commit hash(es) from the implementation
     - Detailed summary paragraph (50-200 words covering what was added/changed)
   - Remove the PEP row from `PEPs/INDEX.md`
   - Delete the PEP directory: `__PEP_DIR__/`

7. **Update status** to "Implemented" in `__PEP_DIR__/summary.md` before deleting (for git history).

## Quality Expectations

- Use the exact entry format from existing `PEPs/IMPLEMENTED/LATEST.md` entries
- aikb updates should be specific and accurate, not boilerplate
- CLAUDE.md updates should only change sections affected by the implementation

## Constraints

- Do not skip aikb updates — they are mandatory
- Do not proceed if implementation steps are incomplete
- Do not modify source code — only documentation and PEP lifecycle files
