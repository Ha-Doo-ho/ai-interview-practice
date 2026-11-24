# Work survey implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task. TDD and verification-before-completion apply.

**Goal:** Introduce the approved two work-behavior questions with six labeled agreement choices while preserving legacy runs.
**Architecture:** An opt-in run-level questionnaire snapshot drives submission, completion, UI and synthesis; legacy definitions remain unchanged.
**Tech Stack:** Python/FastAPI/SQLAlchemy, existing browser JavaScript, pytest and node:test.
**Spec:** `docs/superpowers/specs/2026-11-24-work-survey-design.md`.

## Global constraints

- New set work-behavior-v2 has O-B01/O-B02/O-B03/O-PLAN-COMPARE/O-RESULT-LEARNING.
- Preserve all legacy IDs, labels, original answers, pending request keys and frozen reports.
- No real user database, paid model calls, publishing, Word/PDF changes or spatial questionnaire.
- Experience absence and uncertainty are nonresponses, never agreement positions.

## Tasks

- [x] 1. Add failing synthetic tests for new set generation, selection boundaries, nonresponse separation, legacy prompt preservation and topic linkage. Run RED.
- [x] 2. Add `app/survey_sets.py` for snapshot/resolution; extend creation and survey validation; use the selected set for all progress gates. Run focused Python GREEN.
- [x] 3. Add failing browser DOM checks for five-question new-run creation, six labels, nonresponse choices and legacy resume. Update practice rendering and run creation. Run Node GREEN.
- [x] 4. Resolve synthesis against the run's questionnaire and saved evidence format; add new topic IDs only for the new set and preserve old-set digests. Validate missingness and legacy formats.
- [x] 5. Run affected backend and frontend regressions, read the whole diff and obtain independent review. Fix material findings, record evidence and limitations.

## Review focus

1. Legacy pending POSTs still replay with their original meaning.
2. New set has five required visits; absence/uncertainty count as visits without a numeric position.
3. Switching between new and legacy runs changes definitions and progress together.
4. Wrong-set IDs and incompatible versions cannot be submitted.
5. Old snapshots retain paired/slider/rank data in synthesis; new source wording is never substituted for saved original text.

## Ledger

- Ruling: The active source folder is not a Git repository; use the existing read-only published checkout and Nov 23 source snapshots for comparison, with in-place edits to the active source. No commits or worktree mutations are planned.
- Ruling: New-set creation is explicit so old clients and existing API contracts continue to request the legacy set.
- Ruling: The standard offline launch stalled in tempfile's candidate-name generation. A local artifact wrapper allocates only the attempt directory using a UUID, then runs the unchanged child DB, network, provider and write guards. Direct tests were used to establish the initial RED/GREEN; guarded tests are the final evidence.
- Review: The fresh Astra reviewer found six implementation issues; regression tests first reproduced them. One fix pass addressed conflict/retry missingness, preview missingness, live structured policy, invalid snapshots, old UI routing and labels. Independent re-review found no remaining critical or important defect on supported paths.
- Final evidence: 519 guarded Python checks and 141 Node checks passed. `artifacts/work-survey-20261124/final-summary.json` records source integrity and zero provider attempts/guard violations. No app/test/tool source changed after the final guarded suite started. Browser visual testing and psychometric validation remain separate unperformed work.
