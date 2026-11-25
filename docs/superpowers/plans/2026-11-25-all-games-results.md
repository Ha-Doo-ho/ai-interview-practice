# All games before results implementation plan

**Goal:** Require all eight main games before publishing current-run report results.
**Architecture:** One server completion predicate and an equivalent client predicate gate report operations and read-side projections. Core-five ordering and interview writing remain available; three further main-game types are required for results. Preserve stored evidence and historical finalized reports.
**Tech Stack:** FastAPI, Python, plain browser JavaScript, pytest and Node tests.

## Completion contract

- Five-game-v2: rsp/card three completed rounds each; day/place/bus complete ten questions each; rotation/path/potion at least one complete main attempt of each type. Practice, quick and interrupted attempts do not qualify. An active attempt prevents results.
- Server-driven expiry can complete a game with explicit timeout/unasked outcomes. An explicit stop remains interrupted even at its total deadline.
- Final result generation, linkage, prompt preview and finalization wait for this contract; cached result bodies/history are hidden on unfinished-run reads. Gameplay feedback and source answers remain available.
- Pure legacy flows and previously finalized historical reports remain readable. No keys, user DBs or paid AI are used in verification.

## Tasks

- [x] Add failing completion, endpoint/read-projection, stop-at-deadline and frontend report tests.
- [x] Implement app/game_completion.py; enforce result-only routes and read filtering in main.py; retain core-five start gate.
- [x] Implement client predicate and report/button/card visibility, required wording and cache version.
- [x] Update existing integration fixtures to explicitly finish the three main types before report operations.
- [x] Run focused then full guarded suites; obtain independent tester review; record limits.
- [ ] Publish the checked diff with the expected-head guard and verify the remote tree.
