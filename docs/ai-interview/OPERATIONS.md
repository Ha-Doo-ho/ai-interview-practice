# Local operation and deployment preparation

## Current scope

Verification files are separated from normal practice data. The 2026-09-16 synthetic browser DBs and their companion WAL/SHM files were moved together to `artifacts/browser/legacy-0916/`, without deleting their contents. The resumption regression uses `artifacts/browser/resume-0917.db`. These paths are ignored by version control and are not selected by the standard startup command. The default `interview.db` was preserved.

Same-origin FastAPI + static UI. Bind to 127.0.0.1 for local practice. SQLite default; MySQL SQLAlchemy/PyMySQL target. `.env.example` documents names but the app does not automatically load dotenv files. Set process environment variables explicitly. Never place provider keys in static assets or URLs.

Passwords use a salted password KDF; session tokens are issued by the server and sent in HttpOnly SameSite=Strict cookies. Production HTTPS requires `COOKIE_SECURE=true`. Mutations require the application's custom CSRF header. Do not enable permissive credentialed CORS. Access/error logs must omit request/response bodies; the documented Uvicorn command disables access logs.

## Deletion

Run deletion scrubs raw snapshots, analysis, reports, idempotency responses, cache values and job content. Minimal run/job tombstone identifiers and generation/status metadata prevent late jobs from restoring deleted content; they contain no answer text. Current local implementation retains this minimal metadata until the development DB is discarded. A deployment must define a finite retention period and purge only once no old jobs can execute. There is no separate search index or media store in this MVP.

Account deletion invalidates authentication sessions and removes account credentials together with run content. User-accessible lookup and job completion checks remain required even when cache keys include ownership identifiers.

SQLite deletion is logical content removal, not a forensic secure erase of freed pages/WAL/storage. Do not promise physical erasure from backups or storage sectors. For any deployment, define encrypted backup access, retention and expiration, restore-time deletion replay, and storage-level disposal before accepting real personal data. No production backup system is configured here.

## MySQL preparation

Use a dedicated database, utf8mb4 and an application-specific credential; set `DATABASE_URL` as documented in `.env.example`. Never point test runs at a production database. Migration ownership remains with backend code; inspect `migrations/` before rollout. SQLite tests do not establish MySQL locking/concurrency behavior.

## AI and deployment

Mock is the runnable app mode. Live adapter gates require AI_LIVE_ENABLED, PAID_AI_ENABLED, a server-side key, explicitly allowed model IDs, and known per-run cost/token/time/call budgets. No paid provider execution or operational deployment is authorized by a successful local mock test. Real integration needs a separately reviewed model/budget configuration and provenance verification.

Before external exposure, review HTTPS/cookies, secrets management, abuse/rate controls, database migrations, backup deletion, operational monitoring, load/concurrency and dependency security. These are deployment preparation tasks, not claims that they were performed.
