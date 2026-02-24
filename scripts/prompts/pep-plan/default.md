# PEP Plan Prompt

You are refining the implementation plan for PEP __PEP_NUM__ with deep codebase analysis.

## Your Task

Rewrite the plan with exhaustive, codebase-grounded analysis so every step references real file paths, function signatures, and existing patterns.

1. **Read the PEP:**
   - `__PEP_DIR__/summary.md` — problem, solution, acceptance criteria
   - `__PEP_DIR__/plan.md` — current plan to be rewritten
   - `__PEP_DIR__/research.md` — research findings (if present)

2. **Read all context files** listed in the plan's "Context Files" section.

3. **Perform deep codebase exploration:**
   - Read relevant source files: models, services, views, templates, admin, tasks, CLI commands
   - Cross-reference with `aikb/` documentation for architectural patterns
   - Identify exact file paths, class names, function signatures that will be created or modified
   - Study how similar features were implemented in the codebase

4. **Rewrite `__PEP_DIR__/plan.md`** ensuring:
   - **Context Files** section lists all files an implementer should read (with specific reasons)
   - **Prerequisites** are concrete and verifiable
   - **Implementation Steps** are ordered, checkable `- [ ]` items, each with:
     - **Files**: exact paths to create or modify
     - **Details**: specific implementation details (code structure, field definitions, function signatures)
     - **Verify**: a runnable shell command that confirms the step is complete
   - **Testing** section has concrete test scenarios
   - **Rollback Plan** is actionable
   - **aikb Impact Map** has specific descriptions per file (not just "N/A" — verify each one)
   - **Final Verification** maps every acceptance criterion to a concrete check, includes integration workflows, and regression checks

## Quality Expectations

- Every file path must exist in the codebase (or be clearly marked as "new file")
- Every verification command must be a copy-paste runnable shell command
- Implementation steps should be atomic — completable and verifiable independently
- Reference PEP 0009 (Store Billing) plan quality as the gold standard

## Constraints

- Preserve the plan template structure (all standard sections)
- Do not invent files or patterns that don't exist in the codebase
- Do not modify source code — only rewrite the plan document
- Ground all references in actual codebase state
