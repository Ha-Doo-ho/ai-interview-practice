from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, bindparam, create_engine, delete, event, exists, func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class StoreError(Exception):
    pass


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    pass


class Finalized(StoreError):
    pass


class Deleted(StoreError):
    pass


class InvalidCredentials(StoreError):
    pass


class Validation(StoreError):
    pass


class _OptimisticMiss(Exception):
    pass


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunRow(Base):
    __tablename__ = "practice_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRow(Base):
    __tablename__ = "idempotency_results"
    __table_args__ = (UniqueConstraint("user_id", "run_id", "operation", "idempotency_key", name="uq_idempotency_scope"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobRow(Base):
    __tablename__ = "analysis_jobs"
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    attempt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    run_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CacheRow(Base):
    __tablename__ = "derived_cache"
    __table_args__ = (UniqueConstraint("user_id", "run_id", "attempt_id", "namespace", "cache_key", name="uq_cache_scope"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    attempt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InterviewAnalysisRequestRow(Base):
    """Durable reservation and exact replay for paid interview analysis."""

    __tablename__ = "interview_analysis_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "run_id", "idempotency_key", name="uq_interview_analysis_request"
        ),
    )
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    attempt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    run_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    calls_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_microusd_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    cost, block_size, parallelism = 16384, 8, 1
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=cost, r=block_size, p=parallelism, dklen=32)
    return "$".join(
        ["scrypt", str(cost), str(block_size), str(parallelism), base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(derived).decode()]
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, cost, block_size, parallelism, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.urlsafe_b64decode(salt),
            n=int(cost),
            r=int(block_size),
            p=int(parallelism),
            dklen=32,
        )
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


class Store:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
        if database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _sqlite_options(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        Base.metadata.create_all(self.engine)

    def create_user(self, username: str, password: str) -> dict:
        username = username.strip()
        if len(username) < 2 or len(username) > 64 or len(password) < 8:
            raise Validation("validation_error")
        row = UserRow(user_id=str(uuid4()), username=username, password_hash=_hash_password(password), created_at=_utcnow(), generation=0)
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                session.add(row)
        except IntegrityError as exc:
            raise Conflict("username_taken") from exc
        return {"user_id": row.user_id, "username": row.username}

    def authenticate(self, username: str, password: str) -> dict:
        with Session(self.engine, expire_on_commit=False) as session:
            row = session.scalar(select(UserRow).where(UserRow.username == username.strip(), UserRow.deleted_at.is_(None)))
            if row is None or not _verify_password(password, row.password_hash):
                raise InvalidCredentials("invalid_credentials")
            return {"user_id": row.user_id, "username": row.username}

    def create_session(self, user_id: str, *, lifetime_hours: int = 12) -> str:
        token = secrets.token_urlsafe(32)
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            self._owned_user(session, user_id)
            session.add(SessionRow(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user_id, created_at=_utcnow(), expires_at=_utcnow() + timedelta(hours=lifetime_hours)))
        return token

    def resolve_session(self, token: str | None) -> dict:
        if not token:
            raise InvalidCredentials("unauthorized")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with Session(self.engine, expire_on_commit=False) as session:
            row = session.scalar(
                select(UserRow)
                .join(SessionRow, SessionRow.user_id == UserRow.user_id)
                .where(SessionRow.token_hash == token_hash, SessionRow.expires_at > _utcnow(), UserRow.deleted_at.is_(None))
            )
            if row is None:
                raise InvalidCredentials("unauthorized")
            return {"user_id": row.user_id, "username": row.username}

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            session.execute(delete(SessionRow).where(SessionRow.token_hash == hashlib.sha256(token.encode()).hexdigest()))

    def _owned_user(self, session: Session, user_id: str) -> UserRow:
        row = session.get(UserRow, user_id)
        if row is None or row.deleted_at is not None:
            raise NotFound("not_found")
        return row

    def _owned_run(self, session: Session, user_id: str, run_id: str, *, include_deleted: bool = False) -> RunRow:
        row = session.scalar(select(RunRow).where(RunRow.run_id == run_id, RunRow.user_id == user_id))
        if row is None or (row.deleted_at is not None and not include_deleted):
            raise NotFound("not_found")
        return row

    @staticmethod
    def _snapshot(row: RunRow) -> dict:
        if row.snapshot is None:
            raise NotFound("not_found")
        result = copy.deepcopy(row.snapshot)
        result.update(status=row.status, revision=row.revision, generation=row.generation)
        return result

    def create_run(self, user_id: str, idempotency_key: str | None = None, flow_version: str | None = None) -> dict:
        from .content import DEFINITIONS
        from .game import initial_game_state

        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128):
            raise Validation("validation_error")
        # Stable, user-scoped ID lets the existing primary key arbitrate concurrent
        # retries. Deleted run tombstones retain this ID and prevent resurrection.
        run_id = str(uuid5(NAMESPACE_URL, f"schoolcontest:create-run:{user_id}:{idempotency_key}")) if idempotency_key is not None else str(uuid4())
        request_digest = _digest({"idempotency_key": idempotency_key, **({"flow_version": flow_version} if flow_version else {})})

        def replay(session: Session) -> dict | None:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            self._owned_run(session, user_id, run_id)
            prior = session.scalar(select(IdempotencyRow).where(
                IdempotencyRow.user_id == user_id, IdempotencyRow.run_id == run_id,
                IdempotencyRow.operation == "create_run", IdempotencyRow.idempotency_key == idempotency_key))
            if prior is None or not hmac.compare_digest(prior.request_digest, request_digest):
                raise Conflict("idempotency_conflict")
            return copy.deepcopy(prior.response)

        now, attempt_id = _utcnow(), str(uuid4())
        snapshot = {
            "run_id": run_id,
            "user_id": user_id,
            "attempt_id": attempt_id,
            "status": "in_progress",
            "revision": 0,
            "generation": 0,
            "records": [],
            "game": initial_game_state(DEFINITIONS["game"]),
            "questions": copy.deepcopy(DEFINITIONS["questions"]),
            "analysis": None,
            "report_draft": None,
            "report": None,
            "interview_analysis": None,
            "interview_report": None,
            "runtime_mode": DEFINITIONS["runtime_mode"],
            "created_at": now.isoformat(),
            "completed_at": None,
        }
        if flow_version == "five-game-v2":
            from .appointment_game import initial_appointment_games
            snapshot["flow_version"] = flow_version
            snapshot["appointment_games"] = initial_appointment_games()
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                self._owned_user(session, user_id)
                if idempotency_key is not None:
                    prior = replay(session)
                    if prior is not None:
                        return prior
                session.add(RunRow(run_id=run_id, user_id=user_id, attempt_id=attempt_id, status="in_progress", revision=0, generation=0, snapshot=snapshot, created_at=now, updated_at=now))
                if idempotency_key is not None:
                    session.add(IdempotencyRow(user_id=user_id, run_id=run_id, operation="create_run", idempotency_key=idempotency_key, request_digest=request_digest, response=snapshot, created_at=now))
        except IntegrityError:
            if idempotency_key is None:
                raise
            with Session(self.engine) as session:
                self._owned_user(session, user_id)
                prior = replay(session)
                if prior is not None:
                    return prior
            raise Conflict("idempotency_conflict")
        return copy.deepcopy(snapshot)

    def list_runs(self, user_id: str) -> list[dict]:
        with Session(self.engine, expire_on_commit=False) as session:
            self._owned_user(session, user_id)
            rows = session.scalars(select(RunRow).where(RunRow.user_id == user_id, RunRow.deleted_at.is_(None)).order_by(RunRow.created_at.desc())).all()
            return [self._snapshot(row) for row in rows]

    def get_run(self, user_id: str, run_id: str) -> dict:
        with Session(self.engine, expire_on_commit=False) as session:
            return self._snapshot(self._owned_run(session, user_id, run_id))

    def reserve_interview_analysis(
        self,
        user_id: str,
        run_id: str,
        attempt_id: str,
        expected_revision: int,
        idempotency_key: str,
        request_payload: object,
        requested_mode: str,
        calls_required: int,
        cost_microusd: int,
        max_calls_per_run: int,
        max_cost_microusd: int,
    ) -> dict:
        """Reserve a request and its whole-run budget before provider work.

        SQLite uses an immediate write transaction so different keys cannot
        both observe the same remaining budget. Other databases lock the run
        row before calculating the aggregate.
        """
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
            or not isinstance(idempotency_key, str)
            or not idempotency_key
            or len(idempotency_key) > 128
            or requested_mode not in {"live", "mock"}
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (calls_required, cost_microusd, max_calls_per_run, max_cost_microusd)
            )
        ):
            raise Validation("validation_error")
        request_digest = _digest(request_payload)

        def existing(session: Session) -> dict | None:
            prior = session.scalar(
                select(InterviewAnalysisRequestRow).where(
                    InterviewAnalysisRequestRow.user_id == user_id,
                    InterviewAnalysisRequestRow.run_id == run_id,
                    InterviewAnalysisRequestRow.idempotency_key == idempotency_key,
                )
            )
            if prior is None:
                return None
            if not hmac.compare_digest(prior.request_digest, request_digest):
                raise Conflict("idempotency_conflict")
            if prior.status == "succeeded" and prior.response is not None:
                return {"state": "replay", "response": copy.deepcopy(prior.response)}
            if prior.status == "running":
                raise Conflict("analysis_request_running")
            raise Conflict("analysis_request_failed")

        with Session(self.engine, expire_on_commit=False) as session:
            try:
                if self.engine.dialect.name == "sqlite":
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    session.begin()
                replay = existing(session)
                if replay is not None:
                    session.commit()
                    return replay
                run_query = select(RunRow).where(
                    RunRow.run_id == run_id, RunRow.user_id == user_id
                )
                if self.engine.dialect.name != "sqlite":
                    run_query = run_query.with_for_update()
                row = session.scalar(run_query)
                if row is None or row.deleted_at is not None:
                    raise NotFound("not_found")
                if row.attempt_id != str(attempt_id):
                    raise NotFound("not_found")
                if row.status == "completed":
                    raise Finalized("stale_after_finalize")
                if row.revision != expected_revision:
                    raise Conflict("revision_conflict")
                used_calls, used_cost = session.execute(
                    select(
                        func.coalesce(func.sum(InterviewAnalysisRequestRow.calls_reserved), 0),
                        func.coalesce(func.sum(InterviewAnalysisRequestRow.cost_microusd_reserved), 0),
                    ).where(
                        InterviewAnalysisRequestRow.user_id == user_id,
                        InterviewAnalysisRequestRow.run_id == run_id,
                    )
                ).one()
                if (
                    (calls_required > 0 and used_calls + calls_required > max_calls_per_run)
                    or (cost_microusd > 0 and used_cost + cost_microusd > max_cost_microusd)
                ):
                    raise Validation("budget_exceeded")
                request_id = str(uuid4())
                session.add(
                    InterviewAnalysisRequestRow(
                        request_id=request_id,
                        user_id=user_id,
                        run_id=run_id,
                        attempt_id=str(attempt_id),
                        generation=row.generation,
                        run_revision=row.revision,
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        requested_mode=requested_mode,
                        calls_reserved=calls_required,
                        cost_microusd_reserved=cost_microusd,
                        status="running",
                        response=None,
                        created_at=_utcnow(),
                    )
                )
                session.commit()
                return {"state": "reserved", "request_id": request_id}
            except Exception:
                session.rollback()
                raise

    def get_interview_analysis_replay(
        self,
        user_id: str,
        run_id: str,
        idempotency_key: str,
        request_payload: object,
    ) -> dict | None:
        """Return a completed exact replay, or reject non-retriable keys."""
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128:
            raise Validation("validation_error")
        request_digest = _digest(request_payload)
        with Session(self.engine, expire_on_commit=False) as session:
            self._owned_run(session, user_id, run_id)
            prior = session.scalar(
                select(InterviewAnalysisRequestRow).where(
                    InterviewAnalysisRequestRow.user_id == user_id,
                    InterviewAnalysisRequestRow.run_id == run_id,
                    InterviewAnalysisRequestRow.idempotency_key == idempotency_key,
                )
            )
            if prior is None:
                return None
            if not hmac.compare_digest(prior.request_digest, request_digest):
                raise Conflict("idempotency_conflict")
            if prior.status == "succeeded" and prior.response is not None:
                return copy.deepcopy(prior.response)
            if prior.status == "running":
                raise Conflict("analysis_request_running")
            raise Conflict("analysis_request_failed")

    def assert_interview_analysis_current(self, user_id: str, request_id: str) -> None:
        """Recheck deletion/finalization/revision immediately before each call."""
        with Session(self.engine, expire_on_commit=False) as session:
            reservation = session.scalar(
                select(InterviewAnalysisRequestRow).where(
                    InterviewAnalysisRequestRow.request_id == request_id,
                    InterviewAnalysisRequestRow.user_id == user_id,
                )
            )
            if reservation is None:
                raise Deleted("cancelled_after_deletion")
            row = session.scalar(
                select(RunRow).where(
                    RunRow.run_id == reservation.run_id, RunRow.user_id == user_id
                )
            )
            if row is None or row.deleted_at is not None or row.generation != reservation.generation:
                raise Deleted("cancelled_after_deletion")
            if row.attempt_id != reservation.attempt_id:
                raise NotFound("not_found")
            if row.status == "completed":
                raise Finalized("stale_after_finalize")
            if row.revision != reservation.run_revision:
                raise Conflict("revision_conflict")
            if reservation.status != "running":
                raise Conflict("analysis_request_failed")

    def complete_interview_analysis(self, user_id: str, request_id: str, result: dict, *, kind: str = "interview") -> dict:
        """Atomically publish the result and make its exact HTTP replay durable."""
        if kind not in {"interview", "game"}:
            raise Validation("validation_error")
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                if self.engine.dialect.name == "sqlite":
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    session.begin()
                reservation = session.scalar(
                    select(InterviewAnalysisRequestRow).where(
                        InterviewAnalysisRequestRow.request_id == request_id,
                        InterviewAnalysisRequestRow.user_id == user_id,
                    )
                )
                if reservation is None:
                    raise Deleted("cancelled_after_deletion")
                row = session.scalar(
                    select(RunRow).where(
                        RunRow.run_id == reservation.run_id, RunRow.user_id == user_id
                    )
                )
                if row is None or row.deleted_at is not None or row.generation != reservation.generation:
                    raise Deleted("cancelled_after_deletion")
                if row.attempt_id != reservation.attempt_id:
                    raise NotFound("not_found")
                if row.status == "completed":
                    raise Finalized("stale_after_finalize")
                if row.revision != reservation.run_revision:
                    raise Conflict("revision_conflict")
                if reservation.status != "running":
                    raise Conflict("analysis_request_failed")
                updated = self._snapshot(row)
                field = "interview_analysis" if kind == "interview" else "game_analysis"
                previous = updated.get(field)
                if previous is not None and previous != result:
                    history = updated.setdefault(field + "_history", [])
                    if previous not in history:
                        history.append(copy.deepcopy(previous))
                updated[field] = copy.deepcopy(result)
                if kind == "interview":
                    updated["interview_report"] = copy.deepcopy(result["report"])
                updated["revision"] = row.revision + 1
                row.snapshot = updated
                row.revision = updated["revision"]
                row.updated_at = _utcnow()
                reservation.status = "succeeded"
                reservation.response = copy.deepcopy(updated)
                reservation.completed_at = _utcnow()
                session.commit()
                return copy.deepcopy(updated)
            except Exception:
                session.rollback()
                raise

    def fail_interview_analysis(self, user_id: str, request_id: str, *, error_code: str | None = None) -> None:
        """Keep spent budget while ensuring failed keys can never call again."""
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            reservation = session.scalar(
                select(InterviewAnalysisRequestRow).where(
                    InterviewAnalysisRequestRow.request_id == request_id,
                    InterviewAnalysisRequestRow.user_id == user_id,
                )
            )
            if reservation is not None and reservation.status == "running":
                reservation.status = "failed"
                reservation.response = {'error_code': error_code} if isinstance(error_code, str) and re.fullmatch(r'gemini_http_5[0-9]{2}', error_code) else None
                reservation.completed_at = _utcnow()

    def mutate(
        self,
        user_id: str,
        run_id: str,
        expected_revision: int,
        operation: str,
        idempotency_key: str,
        request_payload: object,
        mutator: Callable[[dict], None],
    ) -> dict:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise Validation("validation_error")
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128:
            raise Validation("validation_error")
        request_digest = _digest(request_payload)
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                prior = session.scalar(
                    select(IdempotencyRow).where(
                        IdempotencyRow.user_id == user_id,
                        IdempotencyRow.run_id == run_id,
                        IdempotencyRow.operation == operation,
                        IdempotencyRow.idempotency_key == idempotency_key,
                    )
                )
                if prior is not None:
                    if not hmac.compare_digest(prior.request_digest, request_digest):
                        raise Conflict("idempotency_conflict")
                    return copy.deepcopy(prior.response)
                row = self._owned_run(session, user_id, run_id)
                if row.status == "completed":
                    raise Finalized("stale_after_finalize")
                if row.revision != expected_revision:
                    raise Conflict("revision_conflict")
                result = self._snapshot(row)
                mutator(result)
                new_status = result.get("status", row.status)
                new_revision = expected_revision + 1
                result.update(revision=new_revision, generation=row.generation, status=new_status)
                changed = session.execute(
                    update(RunRow)
                    .where(
                        RunRow.run_id == run_id,
                        RunRow.user_id == user_id,
                        RunRow.revision == expected_revision,
                        RunRow.deleted_at.is_(None),
                        RunRow.status != "completed",
                    )
                    .values(snapshot=result, revision=new_revision, status=new_status, updated_at=_utcnow())
                )
                if changed.rowcount != 1:
                    raise _OptimisticMiss()
                session.add(
                    IdempotencyRow(
                        user_id=user_id,
                        run_id=run_id,
                        operation=operation,
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        response=result,
                        created_at=_utcnow(),
                    )
                )
                return copy.deepcopy(result)
        except _OptimisticMiss:
            with Session(self.engine, expire_on_commit=False) as session:
                prior = session.scalar(
                    select(IdempotencyRow).where(
                        IdempotencyRow.user_id == user_id,
                        IdempotencyRow.run_id == run_id,
                        IdempotencyRow.operation == operation,
                        IdempotencyRow.idempotency_key == idempotency_key,
                    )
                )
                if prior is not None:
                    if hmac.compare_digest(prior.request_digest, request_digest):
                        return copy.deepcopy(prior.response)
                    raise Conflict("idempotency_conflict")
                current = self._owned_run(session, user_id, run_id)
                if current.status == "completed":
                    raise Finalized("stale_after_finalize")
                raise Conflict("revision_conflict")
        except IntegrityError:
            with Session(self.engine, expire_on_commit=False) as session:
                prior = session.scalar(
                    select(IdempotencyRow).where(
                        IdempotencyRow.user_id == user_id,
                        IdempotencyRow.run_id == run_id,
                        IdempotencyRow.operation == operation,
                        IdempotencyRow.idempotency_key == idempotency_key,
                    )
                )
                if prior is not None and hmac.compare_digest(prior.request_digest, request_digest):
                    return copy.deepcopy(prior.response)
            raise Conflict("idempotency_conflict")

    def get_idempotent_result(
        self,
        user_id: str,
        run_id: str,
        operation: str,
        idempotency_key: str,
        request_payload: object,
    ) -> dict | None:
        """Return an exact prior logical result before expensive work starts."""
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise Validation("validation_error")
        request_digest = _digest(request_payload)
        with Session(self.engine, expire_on_commit=False) as session:
            self._owned_run(session, user_id, run_id)
            prior = session.scalar(
                select(IdempotencyRow).where(
                    IdempotencyRow.user_id == user_id,
                    IdempotencyRow.run_id == run_id,
                    IdempotencyRow.operation == operation,
                    IdempotencyRow.idempotency_key == idempotency_key,
                )
            )
            if prior is None:
                return None
            if not hmac.compare_digest(prior.request_digest, request_digest):
                raise Conflict("idempotency_conflict")
            return copy.deepcopy(prior.response)

    def begin_job(self, user_id: str, run_id: str, attempt_id: str, expected_revision: int, kind: str) -> dict:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            row = self._owned_run(session, user_id, run_id)
            if row.attempt_id != str(attempt_id):
                raise NotFound("not_found")
            if row.status == "completed":
                raise Finalized("stale_after_finalize")
            if row.revision != expected_revision:
                raise Conflict("revision_conflict")
            job = JobRow(job_id=str(uuid4()), user_id=user_id, run_id=run_id, attempt_id=str(attempt_id), kind=kind, run_revision=row.revision, generation=row.generation, status="running", result=None, created_at=_utcnow())
            session.add(job)
            return {"job_id": job.job_id, "user_id": user_id, "run_id": run_id, "attempt_id": str(attempt_id), "run_revision": row.revision, "generation": row.generation, "status": job.status}

    def complete_job(self, user_id: str, job_id: str, result: dict) -> dict:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            job = session.scalar(select(JobRow).where(JobRow.job_id == job_id, JobRow.user_id == user_id))
            if job is None:
                raise NotFound("not_found")
            run_is_current = exists().where(
                RunRow.run_id == job.run_id,
                RunRow.user_id == user_id,
                RunRow.attempt_id == job.attempt_id,
                RunRow.deleted_at.is_(None),
                RunRow.generation == job.generation,
                RunRow.revision == job.run_revision,
            )
            changed = session.execute(
                update(JobRow)
                .where(
                    JobRow.job_id == job_id,
                    JobRow.user_id == user_id,
                    JobRow.status == "running",
                    JobRow.generation == job.generation,
                    run_is_current,
                )
                .values(status="succeeded", result=copy.deepcopy(result), completed_at=_utcnow())
            )
            succeeded = changed.rowcount == 1
            run_id, attempt_id, run_revision, generation = job.run_id, job.attempt_id, job.run_revision, job.generation
        if succeeded:
            return {"job_id": job_id, "status": "succeeded", "run_revision": run_revision, "generation": generation}
        with Session(self.engine, expire_on_commit=False) as session:
            current_job = session.scalar(select(JobRow).where(JobRow.job_id == job_id, JobRow.user_id == user_id))
            current_run = session.scalar(select(RunRow).where(RunRow.run_id == run_id, RunRow.user_id == user_id))
            if (
                current_job is None
                or current_run is None
                or current_run.deleted_at is not None
                or current_run.generation != generation
                or current_job.status == "cancelled_after_deletion"
            ):
                raise Deleted("cancelled_after_deletion")
            if current_run.attempt_id != attempt_id:
                raise NotFound("not_found")
            raise Conflict("revision_conflict")

    def fail_job(self, user_id: str, job_id: str) -> None:
        """Close a failed computation without storing payloads or reviving deleted work."""
        active_run = exists().where(
            RunRow.run_id == JobRow.run_id,
            RunRow.user_id == user_id,
            RunRow.attempt_id == JobRow.attempt_id,
            RunRow.generation == JobRow.generation,
            RunRow.deleted_at.is_(None),
        )
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            session.execute(
                update(JobRow)
                .where(
                    JobRow.job_id == job_id,
                    JobRow.user_id == user_id,
                    JobRow.status == "running",
                    active_run,
                )
                .values(status="failed", result=None, completed_at=_utcnow())
            )

    def get_job_metadata(self, user_id: str, job_id: str) -> dict:
        with Session(self.engine, expire_on_commit=False) as session:
            job = session.scalar(select(JobRow).where(JobRow.job_id == job_id, JobRow.user_id == user_id))
            if job is None:
                raise NotFound("not_found")
            return {"job_id": job.job_id, "status": job.status, "user_id": job.user_id, "run_id": job.run_id, "attempt_id": job.attempt_id, "generation": job.generation, "content_present": job.result is not None}

    def put_cache(self, user_id: str, run_id: str, attempt_id: str, namespace: str, cache_key: str, value: dict) -> None:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            run = self._owned_run(session, user_id, run_id)
            attempt_id = str(attempt_id)
            if run.attempt_id != attempt_id:
                raise NotFound("not_found")
            active_run = exists().where(
                RunRow.run_id == run_id,
                RunRow.user_id == user_id,
                RunRow.attempt_id == attempt_id,
                RunRow.deleted_at.is_(None),
                RunRow.generation == run.generation,
            )
            now = _utcnow()
            changed = session.execute(
                update(CacheRow)
                .where(
                    CacheRow.user_id == user_id,
                    CacheRow.run_id == run_id,
                    CacheRow.attempt_id == attempt_id,
                    CacheRow.namespace == namespace,
                    CacheRow.cache_key == cache_key,
                    CacheRow.generation == run.generation,
                    active_run,
                )
                .values(value=copy.deepcopy(value), created_at=now)
            )
            if changed.rowcount == 1:
                return
            cache_value = bindparam("cache_value", value=copy.deepcopy(value), type_=JSON())
            inserted = session.execute(
                insert(CacheRow).from_select(
                    ["user_id", "run_id", "attempt_id", "namespace", "cache_key", "generation", "value", "created_at"],
                    select(
                        literal(user_id),
                        literal(run_id),
                        literal(attempt_id),
                        literal(namespace),
                        literal(cache_key),
                        RunRow.generation,
                        cache_value,
                        literal(now),
                    ).where(
                        RunRow.run_id == run_id,
                        RunRow.user_id == user_id,
                        RunRow.attempt_id == attempt_id,
                        RunRow.deleted_at.is_(None),
                        RunRow.generation == run.generation,
                    ),
                )
            )
            if inserted.rowcount != 1:
                raise Deleted("cancelled_after_deletion")

    def get_cache(self, user_id: str, run_id: str, attempt_id: str, namespace: str, cache_key: str) -> dict | None:
        with Session(self.engine, expire_on_commit=False) as session:
            run = self._owned_run(session, user_id, run_id)
            attempt_id = str(attempt_id)
            if run.attempt_id != attempt_id:
                raise NotFound("not_found")
            row = session.scalar(
                select(CacheRow).where(CacheRow.user_id == user_id, CacheRow.run_id == run_id, CacheRow.attempt_id == attempt_id, CacheRow.namespace == namespace, CacheRow.cache_key == cache_key, CacheRow.generation == run.generation)
            )
            return copy.deepcopy(row.value) if row else None

    def delete_run(self, user_id: str, run_id: str) -> None:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            row = self._owned_run(session, user_id, run_id)
            row.deleted_at = _utcnow()
            row.generation += 1
            row.status = "deleted"
            row.snapshot = None
            session.execute(delete(IdempotencyRow).where(IdempotencyRow.user_id == user_id, IdempotencyRow.run_id == run_id))
            session.execute(delete(CacheRow).where(CacheRow.user_id == user_id, CacheRow.run_id == run_id))
            session.execute(delete(InterviewAnalysisRequestRow).where(InterviewAnalysisRequestRow.user_id == user_id, InterviewAnalysisRequestRow.run_id == run_id))
            jobs = session.scalars(select(JobRow).where(JobRow.user_id == user_id, JobRow.run_id == run_id)).all()
            for job in jobs:
                job.status = "cancelled_after_deletion"
                job.result = None
                job.completed_at = _utcnow()

    def delete_account(self, user_id: str) -> None:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            user = self._owned_user(session, user_id)
            runs = session.scalars(select(RunRow).where(RunRow.user_id == user_id, RunRow.deleted_at.is_(None))).all()
            now = _utcnow()
            for row in runs:
                row.deleted_at = now
                row.generation += 1
                row.status = "deleted"
                row.snapshot = None
            session.execute(delete(IdempotencyRow).where(IdempotencyRow.user_id == user_id))
            session.execute(delete(CacheRow).where(CacheRow.user_id == user_id))
            session.execute(delete(InterviewAnalysisRequestRow).where(InterviewAnalysisRequestRow.user_id == user_id))
            jobs = session.scalars(select(JobRow).where(JobRow.user_id == user_id)).all()
            for job in jobs:
                job.status = "cancelled_after_deletion"
                job.result = None
                job.completed_at = now
            session.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
            user.username = f"deleted-{user.user_id}"
            user.password_hash = ""
            user.generation += 1
            user.deleted_at = now
