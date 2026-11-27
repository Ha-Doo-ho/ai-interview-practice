# Game journey repair implementation plan

Execute inline with the debugging, test-first and verification skills. User requirement: every main game must finish before interview entry; saved partial progress must remain resumable. No Word/desktop automation, user DB access or live AI calls.

Architecture: retain the existing eight main games and server completion predicate. Reject stale appointment responses before changing module state or clocks, release hidden-panel locks, and provide a persistent journey/recovery panel. Apply the all-eight predicate to interview writes and client navigation/input, preserving existing historical answers and frozen reports. Leaving the page preserves server-confirmed actions; existing game deadlines continue, and interrupted aptitude attempts remain distinct from completed main games.

Confirmed reproduction: deferred appointment GET at card2/revision10 delivered after card3/revision11 hides all three game panels and retains appointment lock. The shared bridge correctly rejects the older run, but the appointment module had already overwritten its own copy.

- [x] Add RED regression for stale GET during card handoff, stale phase/clock, and all-eight interview boundary.
- [x] Guard appointment revision and reconcile locks; keep an always-visible progress/recovery surface so a missing game module cannot produce a blank view.
- [x] Enforce all-eight on fresh answer submissions and route/input access; direct URL and replay paths cannot authorize new early answers. Retain prior stored answers and immutable completed runs.
- [x] Route appointment completion to the remaining three games and offer the interview action only after eight main games complete. Preserve current run selection and saved actions across leaving/relogin.
- [x] Update fixtures that intentionally enabled interviews after only five games. Test actual API lifecycle, game order, interrupted/resumed progress and finalized report compatibility.
- [x] Run focused RED/GREEN, full guarded Python and Node suites, isolated browser handoff/resume checks, and independent Astra review.
- [x] Record verification and publish checked files using expected-head protection; never restart the existing user server without an explicit need.
