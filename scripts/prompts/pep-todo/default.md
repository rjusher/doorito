# PEP Todo Prompt

You are breaking down the implementation plan for PEP __PEP_NUM__ into granular, checkable tasks.

## Your Task

Add a detailed todo checklist to the plan that makes implementation straightforward.

1. **Read the PEP:**
   - `__PEP_DIR__/summary.md` — acceptance criteria and scope
   - `__PEP_DIR__/plan.md` — implementation steps to decompose

2. **Break down each implementation step** into granular, individually completable tasks:
   - Each task should be completable in a single focused session
   - Each task should have a clear done-state
   - Each task should be independently verifiable
   - Group related tasks into phases with descriptive phase headers

3. **Append a "Detailed Todo List" section** to `__PEP_DIR__/plan.md` (before the Completion section) with:
   - Phase headers (`### Phase N: Description`)
   - Checkable items (`- [ ] Task description`)
   - Sub-tasks where needed (indented `- [ ]` items)
   - Include testing, documentation, and verification phases — not just code tasks

## Quality Expectations

- Tasks should be specific enough that an implementer knows exactly what to do
- Avoid duplicating information already in the implementation steps — reference them instead
- Include phases for: setup, implementation (per step), testing, and documentation
- Total task count should reflect the PEP's complexity

## Constraints

- Preserve all existing plan content — append the todo list, do not replace existing sections
- Do not rewrite implementation steps — the todo list complements them
- Do not modify source code or any files outside `__PEP_DIR__/plan.md`
