# Project Enhancement Proposals (PEPs)

Project Enhancement Proposals (PEPs) are the formal mechanism for proposing, documenting, and tracking enhancements to Doorito. Inspired by Python Enhancement Proposals, they provide a structured process for evolving the project.

## Purpose

PEPs serve to:
1. **Document intent** — clearly articulate what a change aims to achieve and why
2. **Enable review** — provide a structured format for discussing proposals before implementation
3. **Track decisions** — maintain a historical record of what was proposed, accepted, or rejected
4. **Guide implementation** — break proposals into actionable implementation plans
5. **Support session resumption** — let AI agents pick up interrupted work without re-exploration

## PEP Structure

Each PEP is a **directory** with **2 required files** and **3 optional files**:

```
PEPs/PEP_NNNN_<title>/
├── summary.md          (required — what and why)
├── research.md         (optional — investigative findings before planning)
├── plan.md             (required — how, checklist, verification)
├── discussions.md      (optional — design decisions, Q&A, open threads)
└── journal.md          (optional — multi-session resumption log)
```

### `summary.md` (required)
The **what and why** of the proposal. Contains:
- Problem statement
- Proposed solution
- Rationale and alternatives considered
- Out of scope (explicit boundaries to prevent scope creep)
- Impact assessment
- Acceptance criteria
- Dependencies (which PEPs this depends on or enables)
- Risk level (Low / Medium / High)
- Status history (lifecycle transitions with dates and notes)

### `plan.md` (required)
The **how, track, and verify** — a single source of truth for implementation. Contains:
- Context files (which `aikb/` files and source files to read before starting)
- Prerequisites
- Implementation steps as a **checkable list** with inline verification commands
- Testing plan
- Rollback plan
- aikb impact map (which `aikb/` files to update after implementation)
- Final verification (acceptance criteria checks, integration checks, regression checks)
- Completion checklist (LATEST.md entry, INDEX.md update, directory removal)

Steps include all relevant detail inline (files to modify, code snippets, model definitions, configuration changes). Organize by step, not by layer — use whatever sub-sections make sense for the PEP.

For large plans, the plan file can be **split into multiple ordered parts** using a letter suffix:
```
plan_a.md   <- first part (applied first)
plan_b.md   <- second part
plan_c.md   <- third part
...
```
The letter (`a`, `b`, `c`, ...) indicates the order in which the parts should be applied. Each part should be self-contained enough to be implemented and verified independently.

### `research.md` (optional)
The **investigative findings** done before (or during) plan creation. Include when the PEP requires codebase exploration, library evaluation, or non-trivial analysis before planning. Skip for straightforward additive PEPs where the implementation path is obvious. Contains:
- Current state analysis (how the codebase currently handles the problem domain)
- Key files & functions (specific paths, classes, and signatures that will be touched)
- Technical constraints (schema limitations, dependency restrictions, performance considerations)
- Pattern analysis (how similar features were implemented elsewhere)
- External research (library evaluations, API documentation, best practices)
- Risk & edge cases (discovered risks and potential pitfalls)
- Recommendations (informed suggestions for the implementation approach)

Research is a snapshot in time — re-verify findings if significant time passes before planning.

### `discussions.md` (optional)
The **Q&A and design decision log**. Include when the PEP has genuine design tensions, unresolved questions, or non-obvious trade-offs. Skip for straightforward additive PEPs. Contains:
- Resolved questions (answered with date and rationale)
- Design decisions (choices made during planning/implementation, with context and alternatives rejected)
- Open threads (active discussions not yet resolved — the single canonical place for unresolved questions)

### `journal.md` (optional)
The **implementation log** for multi-session resumption. Create only when implementation actually spans multiple sessions — do not pre-populate an empty template. Contains:
- Chronological entries appended by agents as they work
- Decisions made with rationale
- Blockers encountered and how they were resolved
- "Left off" notes so the next session knows where to pick up

The journal is never edited retroactively — only appended to.

## Naming Convention

```
PEPs/PEP_NNNN_<title>/
├── summary.md
├── research.md         (if needed)
├── plan.md
├── discussions.md      (if needed)
└── journal.md          (if needed)
```

Or with a split plan:
```
PEPs/PEP_NNNN_<title>/
├── summary.md
├── research.md         (if needed)
├── plan_a.md
├── plan_b.md
├── plan_c.md ...
├── discussions.md      (if needed)
└── journal.md          (if needed)
```

- `NNNN` — zero-padded 4-digit number (e.g., `0001`, `0042`, `0100`)
- `<title>` — lowercase, underscore-separated descriptive title
- Numbers are assigned sequentially
- Letter suffix (`a`, `b`, `c`, ...) for split plans indicates application order

## PEP Lifecycle

```
Proposed -> Accepted -> Implementing -> Implemented
         -> Rejected
         -> Deferred
         -> Withdrawn
```

| Status | Meaning |
|--------|---------|
| Proposed | Ready for review and discussion (summary + plan filled in) |
| Accepted | Approved for implementation |
| Rejected | Declined with documented reasons |
| Deferred | Postponed to a future date |
| Withdrawn | Author withdrew the proposal |
| Implementing | Currently being implemented (check off steps in plan, append to journal if multi-session) |
| Implemented | Fully implemented, documented, and PEP files removed (see below) |

## Effort Sizing

The `Effort` column in INDEX.md uses these rough heuristics:

| Size | Files Changed | Lines of Code | Sessions | Guidance |
|------|--------------|---------------|----------|----------|
| **S** | 1–3 | <100 | 1 | Single-focus change (config, rename, small feature) |
| **M** | 4–10 | <500 | 1–2 | Multi-file feature or moderate refactor |
| **L** | 10–25 | <2000 | 2–4 | Full feature module (views, forms, templates, tests) |
| **XL** | 25+ | 2000+ | 4+ | Consider splitting into sub-PEPs |

These are guidelines, not hard rules. A PEP with few files but complex logic may warrant a higher size. Meta-PEPs use `—` for effort since they are not implemented directly.

## Risk Levels

Each PEP declares a **Risk** level in the summary header table:

| Risk | Meaning | Examples |
|------|---------|----------|
| **Low** | Additive only, no migrations, no shared code changes | New templates, new views, documentation |
| **Medium** | New migrations, touches shared code, new dependencies | New models, service changes, new libraries |
| **High** | Data migration, auth/RBAC changes, breaking changes, external integrations | Schema changes on existing tables, payment integration, multi-tenant changes |

Risk informs review priority — High-risk PEPs warrant more careful review before acceptance.

## Meta-PEPs

A **meta-PEP** is a coordination PEP that is not implemented directly. Instead, it defines the architecture and module map for a group of related sub-PEPs. Meta-PEPs:

- Have `Effort: —` in INDEX.md (no direct implementation)
- Track a **Sub-PEP Status** table in their summary showing all child PEPs and their statuses
- Include a **Shared Patterns** section documenting conventions that all sub-PEPs must follow (e.g., common template patterns, UI conventions, shared components)
- Are closed (moved to IMPLEMENTED/) when **all** sub-PEPs reach Implemented status
- The last sub-PEP's completion checklist should include: "Close parent meta-PEP if all siblings are Implemented"

Sub-PEPs should reference the meta-PEP's shared patterns as context files in their plan.md.

## Amending a PEP During Implementation

Plans may need to change during implementation as new information emerges. When amending the plan:

1. **Add a dated amendment note** at the top of plan.md (below the header):
   ```markdown
   > **Amended YYYY-MM-DD**: Brief description of what changed and why.
   ```
2. **Update the affected steps** in plan.md to match the amended approach.
3. **Log the amendment reason** in the journal (if one exists) with full context.

The plan should remain a living document that reflects the current implementation approach, not a historical artifact. The journal captures the evolution.

## How to Create a PEP

1. **Check `PEPs/INDEX.md`** for the next available number (or use `make pep-new TITLE=name`).
2. **Create the PEP directory** `PEPs/PEP_NNNN_<title>/` and copy `summary.md` and `plan.md` from `PEPs/PEP_0000_template/`.
3. **Fill in the summary** — problem, proposed solution, out of scope, acceptance criteria, risk, dependencies.
4. **Optionally create `research.md`** — if the PEP requires codebase exploration or non-trivial analysis before planning. Copy from `PEP_0000_template/research.md`.
5. **Fill in the plan** — context files, implementation steps with verification commands, aikb impact map, final verification checks.
6. **Optionally create `discussions.md`** — if there are design tensions, unresolved questions, or non-obvious trade-offs. Copy from `PEP_0000_template/discussions.md`.
7. **Set status to Proposed** when the summary and plan are complete.
8. **Add a row to `PEPs/INDEX.md`** with the PEP number, title, status, effort, risk, and dependencies.

## When Implementation Begins

When a PEP is accepted and implementation starts:
1. **Update status** to `Implementing` in the summary file.
2. **Update `PEPs/INDEX.md`** status column.
3. **Read the context files** listed in the plan before writing any code.
4. If the PEP has `research.md`, **read it** for investigative findings and codebase analysis.
5. If the PEP has `discussions.md`, **read it** for prior decisions and open threads.

## During Implementation

1. **Follow the plan** — check off each step after running its verification command.
2. **If the session will span multiple sittings** — create `journal.md` (copy from `PEP_0000_template/journal.md`) and append progress notes and "Left off" summaries.
3. **On session end** — if a journal exists, always append a "Left off" note so the next session can resume.

## When a PEP Is Implemented

When a PEP reaches the **Implemented** status, the following steps are **mandatory**:

### 1. Update Documentation
- **`aikb/` files** — Follow the aikb impact map in the plan file. Update all relevant AI knowledge base files to reflect the new or changed functionality.
- **`CLAUDE.md`** — Update project-level documentation if the PEP changes the architecture, commands, dependencies, or conventions.

### 2. Record in Implemented Log
- **`PEPs/IMPLEMENTED/LATEST.md`** — Add an entry with the PEP number, title, implementation date, git commit hash(es), and a brief summary. Keep only the latest 10 entries; archive older ones to `PAST_YYYYMMDD.md` (date of archival).

### 3. Update Index
- **`PEPs/INDEX.md`** — Remove the PEP's row from the active index.

### 4. Remove PEP Directory
- **Delete** the entire PEP directory `PEPs/PEP_NNNN_<title>/`.
- The full PEP content is preserved in **git history** and can always be retrieved.
- The **`IMPLEMENTED/LATEST.md`** file provides a quick reference without cluttering the directory.

## How to Use PEPs with Claude Code

When working with Claude Code (or any AI agent), PEPs provide structured context:

### Proposing a new enhancement:
> "Create a new PEP for adding API rate limiting. Use the PEP template in PEPs/."

### Implementing an accepted PEP:
> "Implement PEP 0001 following the plan in PEPs/PEP_0001_api_rate_limiting/plan.md"

### Resuming interrupted implementation:
> "Continue implementing PEP 0001. Read the journal to see where the last session left off."

### Reviewing a PEP:
> "Review PEP 0003 and suggest improvements to the plan."

The agent should:
1. Read `summary.md` and `plan.md` (required files)
2. Read `research.md` if it exists (for investigative findings and codebase analysis)
3. Read `discussions.md` if it exists (for prior decisions and open threads)
4. Read `journal.md` if it exists (for session resumption context)
4. Read the context files listed in the plan
5. Cross-reference with existing codebase via `aikb/` documentation
6. Check off steps in the plan as they are completed
7. Create/append to `journal.md` if the session spans multiple sittings
8. After code changes are complete:
   - Follow the aikb impact map in the plan
   - Update `CLAUDE.md` if needed
   - Run the final verification checks in the plan
   - Add an entry to `PEPs/IMPLEMENTED/LATEST.md` with commit hash(es) and summary
   - Remove the PEP's row from `PEPs/INDEX.md`
   - Delete the PEP directory (`PEPs/PEP_NNNN_<title>/`)

## Relationship to specs/ (Historical)

The `specs/` directory previously contained the original feature specifications from the initial design phase. All specs have been migrated: implemented specs are recorded in `PEPs/IMPLEMENTED/LATEST.md` (PEP 0001), and planned specs became PEPs 0007-0012. All future development uses the PEP workflow exclusively.

## Template Files

Templates are located in `PEPs/PEP_0000_template/`:

- [summary.md](PEP_0000_template/summary.md) — Summary template (problem, solution, scope, dependencies) — **required**
- [plan.md](PEP_0000_template/plan.md) — Plan template (steps, verification, aikb impact, completion) — **required**
- [research.md](PEP_0000_template/research.md) — Research template (codebase investigation and findings) — **optional**
- [discussions.md](PEP_0000_template/discussions.md) — Discussions template (Q&A and design decisions) — **optional**
- [journal.md](PEP_0000_template/journal.md) — Journal template (multi-session resumption log) — **optional**

## Helper Scripts

Three Makefile targets automate common PEP operations:

```bash
# Create a new PEP from template (auto-assigns next number, fills in today's date)
make pep-new TITLE=my_feature

# Validate PEP completion checklist (checks LATEST.md, INDEX.md, directory deletion)
make pep-complete PEP=0022

# Archive old IMPLEMENTED/LATEST.md entries when count exceeds 10
make pep-archive
```

Scripts live in `scripts/pep-new.sh`, `scripts/pep-complete.sh`, and `scripts/pep-archive.sh`.

## Reference Files

- [INDEX.md](INDEX.md) — Active PEPs with status, effort, risk, dependencies, and dependency graph
- [IMPLEMENTED/LATEST.md](IMPLEMENTED/LATEST.md) — Log of all implemented PEPs (latest 10; older entries archived to `IMPLEMENTED/PAST_YYYYMMDD.md`)
