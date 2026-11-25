# Eight fixed interview questions implementation plan

> Execute inline with superpowers:executing-plans. Astra 6.2 high independently reviews the completed change.

Goal: retain old displayed questions 1,2,3,4,7,9,13,16. Replace the last sentence of old 13 with old 15's wording and remove the eight standalone questions approved for deletion.

Architecture: keep the three baseline definitions unchanged. Select five supplemental definitions. Keep WM root and its error-checking followup and the spatial root unchanged. Create a v2 repeated-work root and child with new IDs. A POST upgrades an in-progress run once, archiving its original question definitions and preserving all answer records; completed snapshots remain unchanged. The interview UI upgrades legacy supplemental sets through the POST, handles retired drafts without locking current work, and prevents the old 13-question expansion logic from returning. Synthesis/finalization requires current questions for in-progress modern runs so report-direct navigation cannot reuse retired prompts.

Tech stack: existing FastAPI/SQLAlchemy, browser JavaScript, pytest and Node tests, python-docx managed runtime.

Constraints: preserve original source directory, running servers, user DB, past answered definitions and frozen reports. Eight game completion requirement stays unchanged. No live AI calls. Current source is the existing isolated directory game-flow-fix-20261125, which has no .git; do not create or mutate another checkout merely for bookkeeping.

Review focus: old active 16-question run; finalized historical run; repeated upgrades/idempotency; retired pending/rejected/draft state; report-direct access before upgrade.

## Task 1 application
- [x] RED tests for fresh eight, legacy archive/answer preservation, versioned parent, idempotency, completed immutability, and prompt exclusion.
- [x] Implement app/supplemental_interview.py, API gates and html/interview.js. Update older tests to distinguish legacy fixtures and current behavior.
- [x] GREEN targeted Python and frontend tests, then full guarded Python and all frontend tests.

## Task 2 example and report
- [x] Preserve old sixteen-question artifacts in a historical subfolder.
- [x] Generate a new eight-question synthetic example with actual builders, adjust citations and expectations, and rebuild the reader-facing Word with eight questions and current game mapping.
- [x] Astra 6.2 content/source review; record native PDF QA separately when exported.

## Task 3 review and handoff
- [x] Astra 6.2 reviews migration, UI and game gate paths; fix verified substantive issues.
- [x] Save verification and current state. Prepare reviewable changed sources and report. Do not claim a restarted server or remote update unless actually performed.
