# <Plan title>

One-line summary of what this plan delivers.

**Status:** draft | in-progress | review | completed | abandoned
**Owner:** <agent / human>
**Created:** YYYY-MM-DD
**Last updated:** YYYY-MM-DD

## Background & Objective
Why this work exists. What problem it solves. Link to the triggering issue,
PR, or user request if any.

## Technical Approach
**Chosen:** short description of the approach that will be implemented.

**Rejected alternatives:**
- Option A — rejected because ...
- Option B — rejected because ...

## Implementation Steps
- [ ] Step 1 — <description> (complexity: S / M / L)
- [ ] Step 2 — <description> (complexity: S / M / L)
- [ ] Step 3 — <description> (complexity: S / M / L)

## Decision Log
Append-only. Never delete entries; supersede by adding a newer one.

| Date | Decision | Rationale |
|---|---|---|
| YYYY-MM-DD | <what was decided> | <why> |

## Known Risks
- <risk> — mitigation: <how we plan to handle it>

## Acceptance Criteria
Measurable definition of done. Check each box before moving this plan to
`.dev/exec-plans/completed/`.

- [ ] All implementation steps above are checked off
- [ ] `bash .dev/scripts/verify.sh` passes
- [ ] <domain-specific criterion>
- [ ] Decision log covers every non-trivial choice made during implementation
