# Working-memory text interview implementation plan

**Goal:** Add the user-approved experience question and four probes as individually saved text interview answers; audit other games with GPT-6.2 Astra high.
**Spec:** User request in this session approves the exact five Korean prompts described below. No new survey questions or competence scoring requested.
**Architecture:** Keep baseline three questions and their immutable analysis definitions unchanged. Add five optional, fixed supplemental questions without game disclosure. Include them automatically in new five-game runs; existing active runs can add them explicitly. Reuse versioned answer storage and show saved responses separately in the final report.
**Stack:** FastAPI, SQLite/SQLAlchemy, plain JavaScript.

## Constraints and review focus
- Preserve existing answers, finalized reports, baseline counts, AI input and completion policy.
- Separate interview self-report from measured working-memory ability.
- Same revision, owner, CSRF, idempotency and completed-run protections as existing mutations.
- Failed/lost add responses must be recoverable by fetching saved state and retrying without duplicates.
- Preserve exact answer text, revisions, skips, missing answers and source question provenance.
- No Git repository detected. Backups are in artifacts/wm-interview-20261119/before; edit in place, no commit.

## Tasks
- [x] Add regression tests for new/old run question availability, save/reload/revision/access protection, unchanged baseline analysis and frozen final report.
- [x] Implement app/supplemental_interview.py definitions/export; wire store creation, explicit add endpoint and final report export.
- [x] Extend interview UI with five independent answers and existing-run add button; render final supplementary responses; retain baseline counts and unrelated followup locks.
- [x] Run new tests red then green, Python suite and frontend suite; actual browser unavailable (documented).
- [x] Request Astra high adversarial review of changes and resolve material findings.
- [x] Record verification and game coverage audit in docs/ai-interview.

## Completion ledger
- Final Python 500 passed; frontend 132 passed; guarded new API checks 4 passed.
- Astra found legacy analysis and legacy screen routing regressions; repaired app/analysis.py, app/main.py, html/client.js and app/static/app.js. Synthetic rechecks confirm baseline invariance and correct stage routing.
- Ruling: optional supplementary questions preserve existing three-question analysis and stored runs. They do not introduce ability scoring.
- Ruling: no Git metadata exists, so modified local files and retained backups instead of creating a worktree/commit.
- Browser verification blocked by tool session/host availability; API and synthetic DOM verification completed.
