# AI interview text MVP Implementation Plan

## 2026-10-11 current HTML report connection

The scoped plan in `AI_REPORT_CONNECTION.md` is implemented and locally integrated: six saved surveys, two saved rule games, baseline interview and a source-linked report share the same owned run. Original analysis/finalization contracts and raw evidence are preserved. New analysis requests reserve persistent call/cost limits and validate source/version citations. RPS/card remain unmapped. Independent review corrections and synthetic/mock/test-double regression checks passed (Python 274). The subsequent navigation fix connects the current tabs to browser history and preserves interview drafts/in-flight saves; all frontend tests now pass (91), including the updated navigation coverage. The existing preview DB was backed up and preserved across the report restart; navigation changes required no DB access or restart. Live provider execution and human/browser checks are still pending; see CURRENT_STATE.md and VERIFICATION.md for exact evidence and scope.

Goal: implement the supplied MASTER_PROMPT text practice service with preserved evidence and executable acceptance tests.
Architecture: FastAPI serves same-origin HTML/CSS/JS; SQLAlchemy stores authenticated users, immutable original records and separately derived evidence. Deterministic game aggregation and isolated baseline extraction precede comparison and conditioned followups. Mock is the default; paid requests and deployment are disabled.
Tech stack: Python 3.13, FastAPI, SQLAlchemy 2, MySQL/PyMySQL deployment target; SQLite local verification fallback. No existing app stack or Git repository was present.
Spec: ai_interview_codex/MASTER_PROMPT.md and all linked requirements/contracts/harness/setup files (originals preserved).

## Reconnaissance and preservation
- Initial files: empty sch.py, .vscode/settings.json, ai_interview_codex package. Do not modify these.
- No existing root AGENTS.md, AGENTS.override.md or project .codex found. Parent E:/ guidance and default home guidance not found by initial inspection.
- Codex CLI 0.154.0; actual collaboration tool supports Astra/Sol/Terra/Luna/5.5, up to 3 children. No agent_type argument exists here; explicit role instructions are used. Config file discovery is separate from successful generic spawning.
- No Git means no branches/worktrees/commits or diff against original baseline. New paths only.

## Ownership and execution
- Main: root setup, docs, requirements, app/analysis.py, tests/acceptance, integration and verification.
- domain_review (gpt-6-astra/high): read-only independent mapping and later implementation review; no writes.
- backend (gpt-5.6-sol/high): app/__init__.py, app/main.py, app/store.py, app/content.py, app/game.py, app/survey.py, migrations/, tests/test_backend.py. Owns DB migration.
- frontend (gpt-5.6-sol/medium): app/static/ only, browser codepoint helper and accessible full flow.
- QA assigned after a slot is free: tests/harness tooling and independent boundary tests; exact files assigned then.

## Steps and checks
- [x] Read master, requirements, contract, orchestrator, phases, harness and settings; inspect current environment.
- [x] Merge templates into root AGENTS.md and .codex; TOML parsed in the earlier setup. Custom roles actually executed during resumption. Preserve configuration; no further sandbox ACL edits.
- [x] Freeze API below; create critical failing tests before backend/analysis implementation.
- [x] Implement authenticated collection, all four input types, practice + three main game rounds, transaction/idempotency/delete generation guards.
- [x] Implement exact quote validation, mock/live adapter budgets and isolated baseline extraction, conditioned questions, grounded mock reports. Live runtime integration is not enabled.
- [x] Implement UI and run actual browser journey plus keyboard/narrow-screen checks.
- [x] Map all 66 deterministic scenarios to executed tests; classify SCN-051/053 as pending_manual. Full suite: 78 passed; this does not complete the two human studies.
- [x] Independent code review and regression fixes; verification, operating instructions and current state recorded.

Current ownership supersedes the original allocation above: root handled UI and harness; ai_resume owned analysis/provider; backend_resume owned backend/migrations; domain_review_resume performed read-only review. No fourth QA agent was spawned because all three child slots were occupied. Review and tests are evidence for the local SQLite/mock scope only.

## Shared API v1 (frozen implementation interface)
All JSON routes /api. Auth via HttpOnly SameSite=Strict cookie; mutations require X-Requested-With: interview-app. POST register/login {username,password}; GET me; POST logout; DELETE account. Error JSON {error: code}.
GET /definitions => {version, scale, surveys, game, questions, runtime_mode}. Survey item fields item_id, item_version, type, prompt, behavior_id; type definitions embed immutable options/anchors/candidates.
POST /runs {} => run; GET /runs => {runs}; GET /runs/{id} => run including {run_id,status,revision,records,game,questions,report}; DELETE /runs/{id}.
Every run mutation includes idempotency_key, expected_revision. Return full updated run. Revision conflicts 409; unchanged retry returns original logical result.
POST /runs/{id}/surveys {item_id,item_version,response,status:'submitted'|'timed_out'|'skipped',...}. ordinal response {selected_position}; paired {self:{selected_position,status},imagined_others:{selected_position,status}}; slider {final_value,interaction_occurred,explicit_confirmation,change_count}; top-k {selected_ids,selection_events}. Server derives authoritative label/snapshot. Optional elapsed_ms >=0.
POST /runs/{id}/game {action:'start'|'open_info'|'allocate'|'reveal'|'revise'|'next',personal?:0..10,reason?:string,...}. game state {round_index,phase,rounds,events}; each round definition includes practice_or_main, total_resources, time_limit_ms, information, new_information, reward_table. phase awaiting_start/decision/allocated/revision/round_complete/complete. Allocate saves initial decision; reveal records new information; revise may keep same allocation. next opens next round. Server owns sequence, opportunity and score.
POST /runs/{id}/answers {question_id,text,...} stores immutable answer; POST /runs/{id}/analyze {...} calls analysis and returns run with generated followup questions; POST /runs/{id}/finalize {...} validates baseline complete, analysis and freezes run/report. Questions use question_id,question_text,behavior_id,question_mode,asked_criteria,conditioned_on_prior_evidence and disclosure refs.
Record shape {record_id,source_type,source_version,user_id,run_id,attempt_id,item_id,item_version,instructions_version,presentation_id,presentation_order,status,started_at,completed_at,context,data}. Answers data include answer_id/version, question snapshot, text, status and future media refs=null.
Analysis interface: app.analysis.analyze_run(run: dict, definitions: dict) -> {extractions,metrics,comparisons,questions,report,runtime_mode}. Receives owned snapshot only; function internally enforces baseline allowlist. Existing immutable answers/derivations remain stable. Store calls outside transaction then commit using revision/generation guard so deletion wins. DB store needs begin_job/complete_job and cache ownership checks exposed for tests.

## Validation commands
Current offline verification: `.venv/Scripts/python.exe -B -X utf8 -m tools.run_checks`. The launcher selects a fresh SQLite database before importing the global app, blocks external network/model transport, and writes results/harness output into a new `artifacts/offline-checks/run-*/` directory. Use `--sample` for a fresh synthetic example. Direct pytest/sample execution must not be used as proof of DB isolation. Dedicated MySQL verification remains separate and is not supported by this SQLite-only launcher.

Local application startup remains `.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`. That command opens the configured practice DB and is not a test-isolation command. Browser runs require a separately selected test server/database. No paid AI or production deployment.
## 2026-10-11 current scoped task: rule-game persistence

Implementation, automated checks, independent AI review fixes, and local preview startup are complete. Contract: [RULE_GAME_CONNECTION.md](RULE_GAME_CONNECTION.md). Current status and remaining manual checks: [CURRENT_STATE.md](CURRENT_STATE.md). Evidence: [VERIFICATION.md](VERIFICATION.md).

Ownership: root maintained HTML/game/practice integration, frontend tests and shared documentation; rule_game_backend maintained app/rule_games.py, relevant main.py routes/error mapping and test_rule_games.py; rule_game_review was read-only. Existing agents were reused, without recursive delegation. The current workspace was preserved; no Git branch/commit was created. Original surveys/account data and client.js were preserved. Two rule games remain unmapped to B01/B02/B03. Interview/report UI connection is a separate follow-up.

## 2026-10-11 completed scoped task: baseline interview connection

Contract and checked implementation steps: [INTERVIEW_CONNECTION.md](INTERVIEW_CONNECTION.md). Existing owned-run questions/answers APIs were reused; no backend product or database schema changes. A dedicated interview module replaces hardcoded questions and fake submission with per-question saving, original text, immutable correction history, scoped drafts and recoverable requests. Independent practice/game/interview locks protect the shared run.

Completed: context/API review; failing bridge test then implementation; interview module and focused tests; real API journey and three-module integration; independent read-only review and fixes; related Node 73 passed, full safe Python 236 passed, running-server asset/auth-gate checks. Browser/manual interview confirmation remains pending. Same existing server and preview DB were retained. See CURRENT_STATE.md and VERIFICATION.md for evidence and limits.

