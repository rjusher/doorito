# PEP Research Prompt

You are conducting deep codebase research for PEP __PEP_NUM__.

## Your Task

Produce a structured research report that will inform the planning phase.

1. **Read the PEP proposal:**
   - `__PEP_DIR__/summary.md` — understand the problem and proposed solution
   - `__PEP_DIR__/plan.md` — understand the current plan (if filled beyond template)

2. **Read the research template** for expected structure:
   - `PEPs/PEP_0000_template/research.md` — 7 sections to fill

3. **Explore the codebase** to understand the problem domain:
   - Read `aikb/*.md` files relevant to the PEP's domain
   - Read source files (models, services, views, templates) that will be affected
   - Trace data flows through affected components
   - Identify existing patterns that the implementation should follow

4. **Research external resources** if the PEP involves third-party libraries, APIs, or protocols.

5. **Create `__PEP_DIR__/research.md`** with all 7 sections:
   - **Current State Analysis** — how the codebase currently handles the problem domain, relevant models/services/views, existing behavior
   - **Key Files & Functions** — specific file paths, class names, function signatures that will be affected (include line references where helpful)
   - **Technical Constraints** — database schema constraints, dependency restrictions, performance considerations, multi-tenancy implications
   - **Pattern Analysis** — how similar features were implemented elsewhere, patterns to follow (with file path references), patterns to avoid
   - **External Research** — library evaluations, API docs, best practices
   - **Risk & Edge Cases** — what could go wrong, edge cases needing handling, backward compatibility concerns
   - **Recommendations** — informed suggestions for implementation approach, order, and things to verify

6. **Optionally update `__PEP_DIR__/discussions.md`** if the research surfaces open questions or design tensions that need resolution.

## Quality Expectations

- Include specific file paths and line references, not vague descriptions
- Ground all observations in actual codebase state, not assumptions
- Distinguish facts/observations from opinions/recommendations
- Be thorough — this research will be the foundation for the implementation plan

## Constraints

- Do not modify source code or project files outside the PEP directory
- Do not make implementation decisions — those belong in the plan
- Focus on facts and observations
