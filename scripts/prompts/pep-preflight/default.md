# PEP Preflight Prompt

You are performing a pre-implementation validation of PEP __PEP_NUM__'s plan against the current codebase state.

## Your Task

Cross-reference every aspect of the plan against the actual codebase and produce a ready/not-ready verdict.

1. **Read all PEP files:**
   - `__PEP_DIR__/summary.md` — acceptance criteria to validate
   - `__PEP_DIR__/plan.md` — implementation steps to verify
   - `__PEP_DIR__/research.md` (if present) — prior findings to re-verify

2. **Re-read all context files** listed in the plan's "Context Files" section to confirm they still exist and contain expected content.

3. **For every implementation step**, cross-reference against the current codebase:
   - Verify referenced file paths exist
   - Verify function signatures, class names, and import paths still match
   - Verify patterns mentioned in the plan are still current
   - Confirm verification commands are syntactically valid and runnable
   - Check that prerequisites are satisfied

4. **Cross-check acceptance criteria** in `summary.md`:
   - Each criterion has a corresponding verification step in the plan
   - Verification commands would actually test the criterion
   - No criteria are vague or untestable

5. **Produce a structured preflight report** (output to stdout):

   ```
   # Preflight Report — PEP NNNN

   ## Verdict: Ready / Not Ready

   ## Issues Found
   - [ ] Issue 1: description (file:line reference)
   - [ ] Issue 2: description

   ## Stale References
   - [ ] path/to/file.py — referenced in Step N but [doesn't exist / has changed]

   ## Suggestions
   - Suggestion 1
   - Suggestion 2

   ## Acceptance Criteria Coverage
   - [x] Criterion 1 — covered by Step N verification
   - [ ] Criterion 2 — NOT covered, needs verification step
   ```

6. **If issues are found**, optionally update `__PEP_DIR__/plan.md` to fix stale references. Add a dated amendment note.

## Constraints

- This is a read-heavy validation — do not modify source code
- Only fix references in the plan document, not in the codebase
- Be specific about issues — include file paths and line numbers
- If the plan is ready, say so clearly
