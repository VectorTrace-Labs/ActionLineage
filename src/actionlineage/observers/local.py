"""Deterministic local observer adapters."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from actionlineage.domain import EventType, ResourceType, TrustLevel, VerificationStatus
from actionlineage.domain.events import JsonObject, JsonValue


class ObserverOutcome(StrEnum):
    """Observer outcome vocabulary."""

    OBSERVED = "observed"
    UNVERIFIED = "unverified"
    TIMED_OUT = "timed_out"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ObservationOutcome:
    """One observer result ready to normalize into an event payload."""

    observer_identity: str
    resource_type: ResourceType
    resource_identifier: str
    outcome: ObserverOutcome
    observed_state: JsonObject
    limitations: tuple[str, ...]
    trust: TrustLevel = TrustLevel.LOCAL

    @property
    def verification_status(self) -> VerificationStatus:
        if self.outcome == ObserverOutcome.OBSERVED:
            return VerificationStatus.OBSERVED
        if self.outcome == ObserverOutcome.TIMED_OUT:
            return VerificationStatus.TIMED_OUT
        if self.outcome == ObserverOutcome.CONFLICTING:
            return VerificationStatus.CONFLICTING
        return VerificationStatus.UNVERIFIED

    @property
    def event_type(self) -> EventType:
        if self.outcome == ObserverOutcome.OBSERVED:
            return EventType.SIDE_EFFECT_OBSERVED
        if self.outcome == ObserverOutcome.TIMED_OUT:
            return EventType.SIDE_EFFECT_TIMED_OUT
        if self.outcome == ObserverOutcome.CONFLICTING:
            return EventType.SIDE_EFFECT_CONFLICT_DETECTED
        return EventType.SIDE_EFFECT_UNVERIFIED

    def as_payload(self) -> JsonObject:
        return {
            "observer_identity": self.observer_identity,
            "resource": {
                "resource_type": self.resource_type.value,
                "identifier": self.resource_identifier,
            },
            "observed_state": deepcopy(self.observed_state),
            "verification_status": self.verification_status.value,
            "limitations": list(self.limitations),
            "trust": self.trust.value,
        }


@dataclass(frozen=True, slots=True)
class FilesystemObserver:
    """Local filesystem state observer."""

    observer_identity: str = "filesystem_observer"

    def observe_file_state(
        self,
        path: Path,
        *,
        expected_exists: bool | None = None,
    ) -> ObservationOutcome:
        """Observe local file state without treating absence as proof of absence."""

        path = Path(path)
        exists = path.exists()
        state: JsonObject = {
            "exists": exists,
            "path": str(path),
            "is_file": path.is_file() if exists else False,
        }
        if exists:
            state["size_bytes"] = path.stat().st_size
        if expected_exists is True and not exists:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.FILE,
                resource_identifier=str(path),
                outcome=ObserverOutcome.CONFLICTING,
                observed_state=state,
                limitations=("expected file was not observed locally",),
            )
        if expected_exists is False and exists:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.FILE,
                resource_identifier=str(path),
                outcome=ObserverOutcome.CONFLICTING,
                observed_state=state,
                limitations=("file exists despite expected deletion",),
            )
        if exists:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.FILE,
                resource_identifier=str(path),
                outcome=ObserverOutcome.OBSERVED,
                observed_state=state,
                limitations=("local filesystem observation only",),
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.FILE,
            resource_identifier=str(path),
            outcome=ObserverOutcome.UNVERIFIED,
            observed_state=state,
            limitations=("no local file observation was recorded; this is not proof of absence",),
        )

    def timed_out(self, path: Path) -> ObservationOutcome:
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.FILE,
            resource_identifier=str(path),
            outcome=ObserverOutcome.TIMED_OUT,
            observed_state={"path": str(path), "status": "timed_out"},
            limitations=("observer timed out before corroborating file state",),
        )

    def unavailable(self, path: Path, *, reason: str) -> ObservationOutcome:
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.FILE,
            resource_identifier=str(path),
            outcome=ObserverOutcome.UNAVAILABLE,
            observed_state={"path": str(path), "status": "unavailable", "reason": reason},
            limitations=("observer unavailable; no conclusion about side effect",),
        )


@dataclass(slots=True)
class MockHttpReceiverObserver:
    """Fixture HTTP receiver observer for no-network tests."""

    observer_identity: str = "mock_http_receiver"
    receipts: list[JsonObject] = field(default_factory=list)

    def record_receipt(self, *, destination: str, body_digest: str) -> None:
        self.receipts.append({"destination": destination, "body_digest": body_digest})

    def observe_receipt(
        self,
        *,
        destination: str,
        expected_body_digest: str | None = None,
    ) -> ObservationOutcome:
        candidates = tuple(
            receipt for receipt in self.receipts if receipt.get("destination") == destination
        )
        if expected_body_digest is not None:
            exact_matches = tuple(
                receipt
                for receipt in candidates
                if receipt.get("body_digest") == expected_body_digest
            )
            if len(exact_matches) > 1:
                return _ambiguous_http_observation(
                    observer_identity=self.observer_identity,
                    resource_identifier=destination,
                    observed_state={
                        "ambiguous_candidate_count": len(exact_matches),
                        "destination": destination,
                        "expected_body_digest": expected_body_digest,
                    },
                )
            if len(exact_matches) == 1:
                receipt = exact_matches[0]
                return ObservationOutcome(
                    observer_identity=self.observer_identity,
                    resource_type=ResourceType.URL,
                    resource_identifier=destination,
                    outcome=ObserverOutcome.OBSERVED,
                    observed_state={"receipt": receipt},
                    limitations=("mock receiver fixture observation",),
                    trust=TrustLevel.LOCAL,
                )
            if candidates:
                return ObservationOutcome(
                    observer_identity=self.observer_identity,
                    resource_type=ResourceType.URL,
                    resource_identifier=destination,
                    outcome=ObserverOutcome.CONFLICTING,
                    observed_state={
                        "candidate_count": len(candidates),
                        "expected_body_digest": expected_body_digest,
                        "receipt": candidates[0],
                    },
                    limitations=("receiver observed a conflicting body digest",),
                    trust=TrustLevel.LOCAL,
                )
        elif len(candidates) > 1:
            return _ambiguous_http_observation(
                observer_identity=self.observer_identity,
                resource_identifier=destination,
                observed_state={
                    "ambiguous_candidate_count": len(candidates),
                    "destination": destination,
                },
            )

        if len(candidates) == 1:
            receipt = candidates[0]
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=destination,
                outcome=ObserverOutcome.OBSERVED,
                observed_state={"receipt": receipt},
                limitations=("mock receiver fixture observation",),
                trust=TrustLevel.LOCAL,
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.URL,
            resource_identifier=destination,
            outcome=ObserverOutcome.UNVERIFIED,
            observed_state={"destination": destination, "receipt_found": False},
            limitations=("no receiver receipt was recorded; this is not proof of absence",),
            trust=TrustLevel.LOCAL,
        )


@dataclass(slots=True)
class HttpServerLogObserver:
    """Fixture HTTP server-log observer that stores metadata and digests only."""

    observer_identity: str = "http_server_log_observer"
    log_entries: list[JsonObject] = field(default_factory=list)

    def record_access(
        self,
        *,
        url: str,
        method: str,
        status_code: int,
        request_id: str | None = None,
        body_digest: str | None = None,
    ) -> None:
        """Record one fixture access-log entry without raw body or header values."""

        entry: JsonObject = {
            "method": method.upper(),
            "status_code": status_code,
            "url": url,
        }
        if request_id is not None:
            entry["request_id"] = request_id
        if body_digest is not None:
            entry["body_digest"] = body_digest
        self.log_entries.append(entry)

    def observe_access(
        self,
        *,
        url: str,
        method: str | None = None,
        expected_status_code: int | None = None,
        expected_body_digest: str | None = None,
    ) -> ObservationOutcome:
        """Observe request metadata in local fixture server logs."""

        candidates = tuple(
            entry
            for entry in self.log_entries
            if entry.get("url") == url and (method is None or entry.get("method") == method.upper())
        )
        exact_matches = tuple(
            entry
            for entry in candidates
            if not _http_log_conflicts(
                entry,
                expected_body_digest=expected_body_digest,
                expected_status_code=expected_status_code,
            )
        )
        if len(exact_matches) > 1:
            return _ambiguous_http_observation(
                observer_identity=self.observer_identity,
                resource_identifier=url,
                observed_state={
                    "ambiguous_candidate_count": len(exact_matches),
                    "method": method,
                    "url": url,
                },
            )
        if len(exact_matches) == 1:
            entry = exact_matches[0]
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=url,
                outcome=ObserverOutcome.OBSERVED,
                observed_state={"log_entry": entry},
                limitations=("fixture server log observation",),
                trust=TrustLevel.LOCAL,
            )
        if candidates:
            entry = candidates[0]
            conflicts = _http_log_conflicts(
                entry,
                expected_body_digest=expected_body_digest,
                expected_status_code=expected_status_code,
            )
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=url,
                outcome=ObserverOutcome.CONFLICTING,
                observed_state={
                    "candidate_count": len(candidates),
                    "conflicts": conflicts,
                    "log_entry": entry,
                },
                limitations=("server log entry conflicted with expected request metadata",),
                trust=TrustLevel.LOCAL,
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.URL,
            resource_identifier=url,
            outcome=ObserverOutcome.UNVERIFIED,
            observed_state={"method": method, "receipt_found": False, "url": url},
            limitations=("no server log entry was recorded; this is not proof of absence",),
            trust=TrustLevel.LOCAL,
        )


@dataclass(slots=True)
class HttpResponseReadbackObserver:
    """Fixture HTTP response readback observer that stores metadata and digests."""

    observer_identity: str = "http_response_readback_observer"
    responses: list[JsonObject] = field(default_factory=list)

    def record_response(
        self,
        *,
        url: str,
        status_code: int,
        body_digest: str | None = None,
        etag: str | None = None,
    ) -> None:
        """Record a fixture response readback without storing raw response bodies."""

        response: JsonObject = {"status_code": status_code, "url": url}
        if body_digest is not None:
            response["body_digest"] = body_digest
        if etag is not None:
            response["etag"] = etag
        self.responses.append(response)

    def observe_response(
        self,
        *,
        url: str,
        expected_status_code: int | None = None,
        expected_body_digest: str | None = None,
        expected_etag: str | None = None,
    ) -> ObservationOutcome:
        """Observe a fixture response readback."""

        candidates = tuple(response for response in self.responses if response.get("url") == url)
        exact_matches = tuple(
            response
            for response in candidates
            if not _http_response_conflicts(
                response,
                expected_body_digest=expected_body_digest,
                expected_etag=expected_etag,
                expected_status_code=expected_status_code,
            )
        )
        if len(exact_matches) > 1:
            return _ambiguous_http_observation(
                observer_identity=self.observer_identity,
                resource_identifier=url,
                observed_state={
                    "ambiguous_candidate_count": len(exact_matches),
                    "url": url,
                },
            )
        if len(exact_matches) == 1:
            response = exact_matches[0]
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=url,
                outcome=ObserverOutcome.OBSERVED,
                observed_state={"response": response},
                limitations=("fixture response readback observation",),
                trust=TrustLevel.LOCAL,
            )
        if candidates:
            response = candidates[0]
            conflicts = _http_response_conflicts(
                response,
                expected_body_digest=expected_body_digest,
                expected_etag=expected_etag,
                expected_status_code=expected_status_code,
            )
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=url,
                outcome=ObserverOutcome.CONFLICTING,
                observed_state={
                    "candidate_count": len(candidates),
                    "conflicts": conflicts,
                    "response": response,
                },
                limitations=("response readback conflicted with expected metadata",),
                trust=TrustLevel.LOCAL,
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.URL,
            resource_identifier=url,
            outcome=ObserverOutcome.UNVERIFIED,
            observed_state={"response_found": False, "url": url},
            limitations=("no response readback was recorded; this is not proof of absence",),
            trust=TrustLevel.LOCAL,
        )


@dataclass(slots=True)
class WebhookReceiptObserver:
    """Fixture webhook receipt observer that stores digests, not payload bodies."""

    observer_identity: str = "webhook_receipt_observer"
    receipts: list[JsonObject] = field(default_factory=list)

    def record_delivery(
        self,
        *,
        callback_url: str,
        delivery_id: str,
        body_digest: str,
        status_code: int | None = None,
        signature_digest: str | None = None,
    ) -> None:
        """Record a fixture webhook delivery without raw body or header values."""

        receipt: JsonObject = {
            "body_digest": body_digest,
            "callback_url": callback_url,
            "delivery_id": delivery_id,
        }
        if status_code is not None:
            receipt["status_code"] = status_code
        if signature_digest is not None:
            receipt["signature_digest"] = signature_digest
        self.receipts.append(receipt)

    def observe_delivery(
        self,
        *,
        callback_url: str,
        delivery_id: str | None = None,
        expected_body_digest: str | None = None,
        expected_status_code: int | None = None,
    ) -> ObservationOutcome:
        """Observe a webhook delivery receipt from local fixture state."""

        candidates = tuple(
            receipt
            for receipt in self.receipts
            if receipt.get("callback_url") == callback_url
            and (delivery_id is None or receipt.get("delivery_id") == delivery_id)
        )
        exact_matches = tuple(
            receipt
            for receipt in candidates
            if not _webhook_receipt_conflicts(
                receipt,
                expected_body_digest=expected_body_digest,
                expected_status_code=expected_status_code,
            )
        )
        if len(exact_matches) > 1:
            return _ambiguous_http_observation(
                observer_identity=self.observer_identity,
                resource_identifier=callback_url,
                observed_state={
                    "ambiguous_candidate_count": len(exact_matches),
                    "callback_url": callback_url,
                    "delivery_id": delivery_id,
                },
            )
        if len(exact_matches) == 1:
            receipt = exact_matches[0]
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=callback_url,
                outcome=ObserverOutcome.OBSERVED,
                observed_state={"receipt": receipt},
                limitations=("webhook fixture receipt observation",),
                trust=TrustLevel.LOCAL,
            )
        if candidates:
            receipt = candidates[0]
            conflicts = _webhook_receipt_conflicts(
                receipt,
                expected_body_digest=expected_body_digest,
                expected_status_code=expected_status_code,
            )
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.URL,
                resource_identifier=callback_url,
                outcome=ObserverOutcome.CONFLICTING,
                observed_state={
                    "candidate_count": len(candidates),
                    "conflicts": conflicts,
                    "receipt": receipt,
                },
                limitations=("webhook receipt conflicted with expected delivery metadata",),
                trust=TrustLevel.LOCAL,
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.URL,
            resource_identifier=callback_url,
            outcome=ObserverOutcome.UNVERIFIED,
            observed_state={
                "callback_url": callback_url,
                "delivery_id": delivery_id,
                "receipt_found": False,
            },
            limitations=("no webhook receipt was recorded; this is not proof of absence",),
            trust=TrustLevel.LOCAL,
        )


@dataclass(frozen=True, slots=True)
class ProcessObserver:
    """Local process status observer."""

    observer_identity: str = "process_observer"

    def observe_exit(
        self,
        *,
        process_identifier: str,
        return_code: int | None,
        timed_out: bool = False,
    ) -> ObservationOutcome:
        if timed_out:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.PROCESS,
                resource_identifier=process_identifier,
                outcome=ObserverOutcome.TIMED_OUT,
                observed_state={"return_code": return_code, "timed_out": True},
                limitations=("process observer timed out",),
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.PROCESS,
            resource_identifier=process_identifier,
            outcome=ObserverOutcome.OBSERVED,
            observed_state={"return_code": return_code, "timed_out": False},
            limitations=("local process status observation",),
        )


@dataclass(frozen=True, slots=True)
class SqliteReadbackObserver:
    """Local SQLite readback observer for fixture and service-side effects."""

    observer_identity: str = "sqlite_readback_observer"

    def observe_row(
        self,
        database_path: Path,
        *,
        table: str,
        where: dict[str, object],
        expected_exists: bool = True,
    ) -> ObservationOutcome:
        database_path = Path(database_path)
        identifier = f"sqlite://{database_path}#{table}"
        if not database_path.exists():
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.DATABASE_RECORD,
                resource_identifier=identifier,
                outcome=ObserverOutcome.UNVERIFIED,
                observed_state={"database_path": str(database_path), "record_found": False},
                limitations=("no sqlite database was observed; this is not evidence of absence",),
            )

        try:
            count = self._matching_row_count(database_path, table=table, where=where)
        except sqlite3.Error as exc:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.DATABASE_RECORD,
                resource_identifier=identifier,
                outcome=ObserverOutcome.UNAVAILABLE,
                observed_state={
                    "database_path": str(database_path),
                    "table": table,
                    "error_type": type(exc).__name__,
                },
                limitations=("sqlite readback failed; no conclusion about side effect",),
            )

        state: JsonObject = {
            "database_path": str(database_path),
            "table": table,
            "where": {key: str(value) for key, value in where.items()},
            "matching_rows": count,
            "expected_exists": expected_exists,
        }
        if expected_exists and count > 0:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.DATABASE_RECORD,
                resource_identifier=identifier,
                outcome=ObserverOutcome.OBSERVED,
                observed_state=state,
                limitations=("local sqlite readback observation only",),
            )
        if not expected_exists and count == 0:
            return ObservationOutcome(
                observer_identity=self.observer_identity,
                resource_type=ResourceType.DATABASE_RECORD,
                resource_identifier=identifier,
                outcome=ObserverOutcome.OBSERVED,
                observed_state=state,
                limitations=("local sqlite readback observed no matching row at query time",),
            )
        return ObservationOutcome(
            observer_identity=self.observer_identity,
            resource_type=ResourceType.DATABASE_RECORD,
            resource_identifier=identifier,
            outcome=ObserverOutcome.CONFLICTING,
            observed_state=state,
            limitations=("sqlite readback did not match expected row state",),
        )

    def _matching_row_count(
        self,
        database_path: Path,
        *,
        table: str,
        where: dict[str, object],
    ) -> int:
        if not where:
            raise sqlite3.OperationalError("sqlite readback requires at least one predicate")
        table_name = _sqlite_identifier(table)
        clauses = [f"{_sqlite_identifier(column)} = ?" for column in where]
        values = tuple(where.values())
        sql = f"select count(*) from {table_name} where {' and '.join(clauses)}"
        with closing(sqlite3.connect(database_path)) as connection:
            row = connection.execute(sql, values).fetchone()
        return int(row[0]) if row is not None else 0


def _sqlite_identifier(value: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
        raise sqlite3.OperationalError("sqlite identifier is invalid")
    return value


def _ambiguous_http_observation(
    *,
    observer_identity: str,
    resource_identifier: str,
    observed_state: JsonObject,
) -> ObservationOutcome:
    return ObservationOutcome(
        observer_identity=observer_identity,
        resource_type=ResourceType.URL,
        resource_identifier=resource_identifier,
        outcome=ObserverOutcome.UNVERIFIED,
        observed_state=observed_state,
        limitations=("multiple plausible observer records matched; correlation remains ambiguous",),
        trust=TrustLevel.LOCAL,
    )


def _webhook_receipt_conflicts(
    receipt: JsonObject,
    *,
    expected_body_digest: str | None,
    expected_status_code: int | None,
) -> list[JsonValue]:
    conflicts: list[JsonValue] = []
    if expected_body_digest is not None and receipt.get("body_digest") != expected_body_digest:
        conflicts.append("body_digest")
    if expected_status_code is not None and receipt.get("status_code") != expected_status_code:
        conflicts.append("status_code")
    return conflicts


def _http_log_conflicts(
    entry: JsonObject,
    *,
    expected_body_digest: str | None,
    expected_status_code: int | None,
) -> list[JsonValue]:
    conflicts: list[JsonValue] = []
    if expected_body_digest is not None and entry.get("body_digest") != expected_body_digest:
        conflicts.append("body_digest")
    if expected_status_code is not None and entry.get("status_code") != expected_status_code:
        conflicts.append("status_code")
    return conflicts


def _http_response_conflicts(
    response: JsonObject,
    *,
    expected_body_digest: str | None,
    expected_etag: str | None,
    expected_status_code: int | None,
) -> list[JsonValue]:
    conflicts: list[JsonValue] = []
    if expected_body_digest is not None and response.get("body_digest") != expected_body_digest:
        conflicts.append("body_digest")
    if expected_etag is not None and response.get("etag") != expected_etag:
        conflicts.append("etag")
    if expected_status_code is not None and response.get("status_code") != expected_status_code:
        conflicts.append("status_code")
    return conflicts
