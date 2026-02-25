# PEP Draft Prompt

You are drafting a new Project Enhancement Proposal (PEP) for Doorito.

## Your Task

Given the following description of a proposed enhancement:

> __PEP_DESC__

1. **Infer a concise, descriptive title** from the description.
   - Format: lowercase, underscores, alphanumeric only (e.g., `store_billing`, `multi_platform_sync`, `realtime_notifications`)
   - This must match the normalization that `scripts/pep-new.sh` applies: `tr '[:upper:]' '[:lower:]' | tr ' ' '_' | tr -cd 'a-z0-9_'`
   - Keep it short (2-4 words) but descriptive enough to identify the feature

2. **Run `scripts/pep-new.sh <inferred_title>`** to create the PEP directory from templates. This auto-assigns the next available PEP number and creates `summary.md` and `plan.md` from templates.

3. **Read reference files** to understand project conventions:
   - `PEPs/PEP_0000_template/summary.md` — summary structure and sections
   - `PEPs/ABOUT.md` — PEP governance rules
   - `PEPs/INDEX.md` — active PEPs (for style reference and to add the new row)
   - `aikb/architecture.md` — project architecture
   - `aikb/models.md` — existing models
   - `aikb/services.md` — existing services
   - `aikb/conventions.md` — coding conventions

4. **Read an existing well-written PEP for quality reference.** PEP 0009 (Store Billing) in git history is the gold standard. If other active PEPs exist in `PEPs/`, read their summary for style reference.

5. **Fill in the newly created `summary.md`** with all sections:
   - Problem Statement — clear, specific, motivated
   - Proposed Solution — high-level description with key components
   - Rationale — why this approach over others
   - Alternatives Considered — at least 2 alternatives with pros/cons/rejection reason
   - Impact Assessment — affected components, migration impact, performance impact
   - Out of Scope — explicit boundaries
   - Acceptance Criteria — specific, testable `- [ ]` checklist items
   - Status History — set to Proposed with today's date

6. **Leave `plan.md` as-is.** The template created by `pep-new.sh` already contains the correct structure. Do NOT fill in or modify `plan.md` — it will be completed later during the planning phase (`make claude-pep-plan`).

7. **Add a row to `PEPs/INDEX.md`** in the table with: PEP number, title, status (Proposed), estimated effort, risk level, and dependencies.

## Constraints

- Do not modify any files outside the new PEP directory and `PEPs/INDEX.md`
- Do not change the project's architecture or existing code
- Set the status to "Proposed" — do not start implementing
- Use the description provided above as the basis; do not invent unrelated features
- Ensure acceptance criteria are testable, not vague
