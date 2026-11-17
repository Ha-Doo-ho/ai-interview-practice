-- Logical initial schema for MySQL 8. SQLite local tests use the same SQLAlchemy model metadata.
CREATE TABLE users (
  user_id VARCHAR(36) PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  generation INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL,
  deleted_at DATETIME(6) NULL
);
CREATE TABLE auth_sessions (
  token_hash VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  INDEX ix_auth_sessions_user_id (user_id),
  CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE practice_runs (
  run_id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  attempt_id VARCHAR(36) NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  generation INTEGER NOT NULL DEFAULT 0,
  snapshot JSON NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted_at DATETIME(6) NULL,
  INDEX ix_practice_runs_user_id (user_id),
  CONSTRAINT fk_practice_runs_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE idempotency_results (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  run_id VARCHAR(36) NOT NULL,
  operation VARCHAR(64) NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  request_digest VARCHAR(64) NOT NULL,
  response JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_idempotency_scope (user_id, run_id, operation, idempotency_key)
);
CREATE TABLE analysis_jobs (
  job_id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  run_id VARCHAR(36) NOT NULL,
  attempt_id VARCHAR(64) NOT NULL,
  kind VARCHAR(64) NOT NULL,
  run_revision INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  status VARCHAR(40) NOT NULL,
  result JSON NULL,
  created_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  INDEX ix_analysis_jobs_owner (user_id, run_id)
);
CREATE TABLE derived_cache (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  run_id VARCHAR(36) NOT NULL,
  attempt_id VARCHAR(64) NOT NULL,
  namespace VARCHAR(64) NOT NULL,
  cache_key VARCHAR(128) NOT NULL,
  generation INTEGER NOT NULL,
  value JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_cache_scope (user_id, run_id, attempt_id, namespace, cache_key)
);
