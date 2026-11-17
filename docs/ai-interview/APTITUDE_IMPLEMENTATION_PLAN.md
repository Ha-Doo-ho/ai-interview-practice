# Three additional games implementation plan (2026-11-17)

Spec: `docs/ai-interview/GAME_IMPLEMENTATION_SPEC.md` (the request's `ai-interviwe` spelling resolves here).

Architecture: retain FastAPI/SQLite run snapshots and vanilla JS. Add optional games within the existing game tab, independent of the five-game completion gate. Existing games, AI input contracts and scores remain intact. New attempts belong to the logged-in user's run, use Store.mutate revision/idempotency protection, and are visible in game results and the report tab. Completed runs remain immutable.

Decisions: potion has a project-defined 15-second question timer; rotation/path use 240-second total timers. Leaving the screen does not pause time. Stop preserves an interrupted attempt; restart creates another attempt. Practice is a separate unscored attempt. Difficulty easy/hard changes generators, never score weights. No production database changes, paid AI calls or deployment. This folder is not a Git checkout; retain original files via targeted backup before editing.

## Ownership and interfaces

- Algorithms worker: `app/aptitude_rotation.py`, `app/aptitude_path.py`, `app/aptitude_potion.py`, `tests/test_aptitude_algorithms.py`. Each exports `generate(rng, number, difficulty, config)` -> private question dict, `public_question(q, practice=False)` -> safe problem data, `evaluate(q, response)` -> {correct, metrics, ...}. Worker coordinates exact payloads with state worker/root.
- State worker: `app/aptitude_games.py`, `app/aptitude_config.py`, `tests/test_aptitude_state.py`. Exports `apply_action(snapshot, body)`, `public_state(state)`, `definitions()`. Snapshot key `aptitude_games`: {version, attempts:[...]}. Action start uses {game_type, mode:practice|main|quick, difficulty:easy|hard}; subsequent actions use {attempt_id, question_id, action, ...}. All are server timed, public redacted, append-only attempts. Include submit/next/stop/timeout and server-recorded manipulation actions.
- Root: API integration in `app/main.py`, frontend module/style and `html/index.html`, additive result display on report tab, API/frontend tests, verification documentation. GET `/api/aptitude-games/definitions`; GET/POST `/api/runs/{run_id}/aptitude-games`. POST returns public run; GET returns {run, server_time_ms}.

## Execution

- [x] Write and run failing algorithm tests; implement geometry, BFS minima, path simulation/validated fixtures and seeded probability model; verify.
- [x] Write and run failing state tests; implement config, practice exclusion, scoring floors, timers, operation limits, retained attempts and summaries; verify.
- [x] Add guarded run API and UI selection/instructions/practice/main/result screens with mouse/keyboard support, retry journal and refresh restoration; test full journeys and ownership.
- [x] Run existing Python/frontend suites and the executable scenario harness; review final code, document actual outcomes and limitations.

## Review focus

Hidden potion probabilities/seeds must never appear while playing; retries cannot score twice; stale tabs cannot settle the wrong question; timeout must use server time; interruption/restart must retain prior evidence. Report gameplay counts independently; never produce personality/hiring/percentile claims.

## Official versus project rules

Official source `https://www.jobda.im/info/406` confirms 45-degree turns, hidden rotation display, route reflections by 90 degrees/shared fences, four-card probabilistic prediction, and named task purposes. Linked official pages 336/338/339 provide video introductions. Numeric scores, timers, counts, geometry, fixture boards, probability table, stop/restart policy and normalization are project choices, not official scoring or validated psychological measurement.
