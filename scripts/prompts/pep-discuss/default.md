# PEP Discuss Prompt

You are identifying and resolving open questions, design tensions, and ambiguities for PEP __PEP_NUM__.

## Your Task

Review the PEP proposal for unresolved issues and produce structured resolutions.

1. **Read all PEP files:**
   - `__PEP_DIR__/summary.md` — proposed solution, rationale, acceptance criteria
   - `__PEP_DIR__/plan.md` — implementation steps, context files, aikb impact
   - `__PEP_DIR__/research.md` (if present) — codebase analysis and recommendations
   - `__PEP_DIR__/discussions.md` (if present) — prior resolved questions and open threads

2. **Read the discussions template** for expected format:
   - `PEPs/PEP_0000_template/discussions.md` — Resolved Questions, Design Decisions, Open Threads

3. **Scan for issues** across the proposal:
   - Ambiguous language: "TBD", "maybe", "possibly", "or", "could"
   - Unresolved alternatives in the rationale or alternatives section
   - Missing details in acceptance criteria (vague or untestable criteria)
   - Implementation steps without verification commands
   - Conflicting information between summary and plan
   - Assumptions not validated against the codebase
   - Dependencies or prerequisites that are unclear
   - Risk areas without mitigation strategies

4. **For each issue found**, analyze the codebase and project conventions to form a recommendation. Read relevant source files if needed.

5. **Create or update `__PEP_DIR__/discussions.md`** with:
   - **Resolved Questions**: issues you can definitively resolve — include date, answer, and rationale
   - **Design Decisions**: significant trade-offs you've identified — include context, decision, and alternatives rejected
   - **Open Threads**: questions that need human input to resolve — include context, options, and status

6. **Optionally amend `summary.md` or `plan.md`** to reflect resolved decisions. If you amend these files, add a dated amendment note (e.g., `<!-- Amendment 2026-02-23: Updated based on discussions -->`).

## Constraints

- Never delete existing entries in `discussions.md` — append only
- Clearly separate resolved issues from open threads
- Flag items that require human input rather than making assumptions
- Do not modify source code or project files outside the PEP directory
- Focus on the proposal quality, not implementation
