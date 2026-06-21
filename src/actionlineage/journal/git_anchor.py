"""Git-backed statements for trusted journal anchors."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from actionlineage.domain import deterministic_json_bytes
from actionlineage.domain.events import JsonObject
from actionlineage.journal.anchors import JournalAnchorError

GIT_ANCHOR_STATEMENT_VERSION = "actionlineage.dev/git-anchor-statement-v1"

type GitAnchorIssueCode = Literal[
    "anchor_file_missing",
    "anchor_hash_mismatch",
    "git_anchor_blob_missing",
    "git_anchor_blob_mismatch",
    "git_command_failed",
    "git_commit_missing",
    "git_ref_mismatch",
]


@dataclass(frozen=True, slots=True)
class GitAnchorStatement:
    """Reviewable statement that ties an anchor file to a Git commit.

    ActionLineage does not create commits, tags, notes, or push refs. Callers can
    store this deterministic sidecar in a protected Git workflow or release
    artifact, then verify that the referenced anchor bytes and commit still
    match the statement.
    """

    anchor_path: str
    anchor_git_path: str
    anchor_sha256: str
    repository_path: str
    git_ref: str
    git_commit: str
    created_at: datetime
    statement_version: str = GIT_ANCHOR_STATEMENT_VERSION

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible statement object."""

        return {
            "anchor_git_path": self.anchor_git_path,
            "anchor_path": self.anchor_path,
            "anchor_sha256": self.anchor_sha256,
            "created_at": _timestamp(self.created_at),
            "git_commit": self.git_commit,
            "git_ref": self.git_ref,
            "repository_path": self.repository_path,
            "statement_version": self.statement_version,
        }


@dataclass(frozen=True, slots=True)
class GitAnchorVerificationIssue:
    """One Git anchor statement verification issue."""

    code: GitAnchorIssueCode
    message: str
    expected: str | None = None
    actual: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue."""

        return {
            "actual": self.actual,
            "code": self.code,
            "expected": self.expected,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class GitAnchorVerificationResult:
    """Result of verifying a Git anchor statement."""

    ok: bool
    issues: tuple[GitAnchorVerificationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": self.ok,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def create_git_anchor_statement(
    anchor_path: Path,
    *,
    repository_path: Path = Path("."),
    ref: str = "HEAD",
    created_at: datetime | None = None,
) -> GitAnchorStatement:
    """Create a deterministic statement tying anchor bytes to a Git commit."""

    if not anchor_path.exists():
        raise JournalAnchorError("cannot create Git anchor statement for a missing anchor file")

    commit = _git_rev_parse_commit(repository_path, ref)
    anchor_git_path = _repo_relative_path(repository_path, anchor_path)
    anchor_hash = _file_sha256(anchor_path)
    committed_hash = _git_file_sha256(repository_path, commit, anchor_git_path)
    if committed_hash is None:
        raise JournalAnchorError("anchor file is not present in the recorded Git commit")
    if committed_hash != anchor_hash:
        raise JournalAnchorError("anchor file bytes do not match the recorded Git commit")
    return GitAnchorStatement(
        anchor_git_path=anchor_git_path,
        anchor_path=str(anchor_path),
        anchor_sha256=anchor_hash,
        repository_path=str(repository_path),
        git_ref=ref,
        git_commit=commit,
        created_at=created_at or datetime.now(UTC),
    )


def write_git_anchor_statement(
    statement: GitAnchorStatement,
    statement_path: Path,
) -> None:
    """Write a Git anchor statement as deterministic JSON."""

    statement_path.parent.mkdir(parents=True, exist_ok=True)
    statement_path.write_bytes(deterministic_json_bytes(statement.as_dict()) + b"\n")


def load_git_anchor_statement(statement_path: Path) -> GitAnchorStatement:
    """Load a Git anchor statement from JSON."""

    raw = json.loads(statement_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise JournalAnchorError("Git anchor statement must be a JSON object")
    return _statement_from_dict(raw)


def verify_git_anchor_statement(
    statement: GitAnchorStatement,
    *,
    anchor_path: Path | None = None,
    repository_path: Path | None = None,
    ref: str | None = None,
) -> GitAnchorVerificationResult:
    """Verify a Git anchor statement against local anchor bytes and Git objects.

    If `ref` is supplied, it must resolve to the committed object recorded in
    the statement. Without `ref`, verification only requires that the recorded
    commit object is present in the repository, so old statements remain
    verifiable after later commits.
    """

    issues: list[GitAnchorVerificationIssue] = []
    effective_anchor_path = anchor_path or Path(statement.anchor_path)
    effective_repository_path = repository_path or Path(statement.repository_path)

    if not effective_anchor_path.exists():
        issues.append(
            GitAnchorVerificationIssue(
                code="anchor_file_missing",
                message="anchor file referenced by Git statement is missing",
                expected=statement.anchor_sha256,
            )
        )
    else:
        actual_anchor_hash = _file_sha256(effective_anchor_path)
        if actual_anchor_hash != statement.anchor_sha256:
            issues.append(
                GitAnchorVerificationIssue(
                    code="anchor_hash_mismatch",
                    message="anchor file hash does not match Git statement",
                    expected=statement.anchor_sha256,
                    actual=actual_anchor_hash,
                )
            )

    repo_check = _run_git(effective_repository_path, "rev-parse", "--git-dir")
    if not repo_check.ok:
        issues.append(
            GitAnchorVerificationIssue(
                code="git_command_failed",
                message="Git repository could not be inspected",
            )
        )
        return GitAnchorVerificationResult(ok=False, issues=tuple(issues))

    commit_check = _run_git(
        effective_repository_path,
        "cat-file",
        "-e",
        f"{statement.git_commit}^{{commit}}",
    )
    if not commit_check.ok:
        issues.append(
            GitAnchorVerificationIssue(
                code="git_commit_missing",
                message="Git commit recorded in anchor statement is not present",
                expected=statement.git_commit,
            )
        )
    else:
        committed_hash = _git_file_sha256(
            effective_repository_path,
            statement.git_commit,
            statement.anchor_git_path,
        )
        if committed_hash is None:
            issues.append(
                GitAnchorVerificationIssue(
                    code="git_anchor_blob_missing",
                    message="anchor file is not present in the recorded Git commit",
                    expected=statement.anchor_git_path,
                )
            )
        elif committed_hash != statement.anchor_sha256:
            issues.append(
                GitAnchorVerificationIssue(
                    code="git_anchor_blob_mismatch",
                    message="anchor bytes in the recorded Git commit do not match the statement",
                    expected=statement.anchor_sha256,
                    actual=committed_hash,
                )
            )

    if ref is not None:
        ref_resolution = _run_git(
            effective_repository_path,
            "rev-parse",
            "--verify",
            f"{ref}^{{commit}}",
        )
        if not ref_resolution.ok:
            issues.append(
                GitAnchorVerificationIssue(
                    code="git_command_failed",
                    message="Git ref could not be resolved for anchor statement verification",
                    expected=ref,
                )
            )
        else:
            actual_commit = ref_resolution.stdout.strip()
            if actual_commit != statement.git_commit:
                issues.append(
                    GitAnchorVerificationIssue(
                        code="git_ref_mismatch",
                        message="Git ref does not resolve to the committed anchor statement",
                        expected=statement.git_commit,
                        actual=actual_commit,
                    )
                )

    return GitAnchorVerificationResult(ok=not issues, issues=tuple(issues))


@dataclass(frozen=True, slots=True)
class _GitResult:
    ok: bool
    stdout: str


def _run_git(repository_path: Path, *args: str) -> _GitResult:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_path), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JournalAnchorError("Git command failed during anchor statement handling") from exc
    return _GitResult(ok=result.returncode == 0, stdout=result.stdout)


@dataclass(frozen=True, slots=True)
class _GitBytesResult:
    ok: bool
    stdout: bytes


def _run_git_bytes(repository_path: Path, *args: str) -> _GitBytesResult:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_path), *args],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JournalAnchorError("Git command failed during anchor statement handling") from exc
    return _GitBytesResult(ok=result.returncode == 0, stdout=result.stdout)


def _git_rev_parse_commit(repository_path: Path, ref: str) -> str:
    result = _run_git(repository_path, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not result.ok:
        raise JournalAnchorError("cannot resolve Git ref for anchor statement")
    return result.stdout.strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _git_file_sha256(repository_path: Path, commit: str, git_path: str) -> str | None:
    result = _run_git_bytes(repository_path, "show", f"{commit}:{git_path}")
    if not result.ok:
        return None
    digest = hashlib.sha256(result.stdout).hexdigest()
    return f"sha256:{digest}"


def _repo_relative_path(repository_path: Path, anchor_path: Path) -> str:
    repo_root_result = _run_git(repository_path, "rev-parse", "--show-toplevel")
    if not repo_root_result.ok:
        raise JournalAnchorError("cannot inspect Git repository for anchor statement")
    repo_root = Path(repo_root_result.stdout.strip()).resolve()
    resolved_anchor = anchor_path.resolve()
    try:
        relative = resolved_anchor.relative_to(repo_root)
    except ValueError as exc:
        raise JournalAnchorError("anchor file must be inside the Git repository") from exc
    return relative.as_posix()


def _statement_from_dict(raw: dict[str, Any]) -> GitAnchorStatement:
    created_at_raw = _required_str(raw, "created_at")
    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).astimezone(UTC)
    statement_version = raw.get("statement_version", GIT_ANCHOR_STATEMENT_VERSION)
    if not isinstance(statement_version, str) or not statement_version:
        raise JournalAnchorError("Git anchor statement field is required: statement_version")
    return GitAnchorStatement(
        anchor_git_path=_required_str(raw, "anchor_git_path"),
        anchor_path=_required_str(raw, "anchor_path"),
        anchor_sha256=_required_str(raw, "anchor_sha256"),
        created_at=created_at,
        git_commit=_required_str(raw, "git_commit"),
        git_ref=_required_str(raw, "git_ref"),
        repository_path=_required_str(raw, "repository_path"),
        statement_version=statement_version,
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise JournalAnchorError(f"Git anchor statement field is required: {key}")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise JournalAnchorError("Git anchor statement timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
