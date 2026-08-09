"""Self-test findings: structured bug/issue records with persistence.

Every finding is a triage item, not a verdict. Findings start ``open`` and
become ``confirmed`` / ``dismissed`` / ``fixed`` only after user review.
"""

import datetime
import json
import os
import threading
import uuid

FINDINGS_DIR_ENV = "JARVIS_SELF_TEST_DIR"
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "self_test")

STATUS_OPEN = "open"
STATUS_CONFIRMED = "confirmed"
STATUS_DISMISSED = "dismissed"
STATUS_FIXED = "fixed"
VALID_STATUSES = {STATUS_OPEN, STATUS_CONFIRMED, STATUS_DISMISSED, STATUS_FIXED}

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
VALID_SEVERITIES = {SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO}

_lock = threading.Lock()


def _store_dir() -> str:
    return os.getenv(FINDINGS_DIR_ENV) or DEFAULT_DIR


def _findings_path() -> str:
    return os.path.join(_store_dir(), "findings.jsonl")


def _runs_path() -> str:
    return os.path.join(_store_dir(), "runs.jsonl")


def _now() -> str:
    return datetime.datetime.now().isoformat()


class Finding:
    __slots__ = (
        "id",
        "severity",
        "category",
        "title",
        "detail",
        "source",
        "evidence",
        "status",
        "created_at",
        "updated_at",
    )

    def __init__(
        self,
        severity: str,
        category: str,
        title: str,
        detail: str = "",
        source: str = "",
        evidence: dict | None = None,
        status: str = STATUS_OPEN,
        finding_id: str | None = None,
        created_at: str | None = None,
    ):
        self.id = finding_id or uuid.uuid4().hex[:12]
        self.severity = severity if severity in VALID_SEVERITIES else SEVERITY_INFO
        self.category = category
        self.title = title
        self.detail = detail
        self.source = source
        self.evidence = evidence or {}
        self.status = status if status in VALID_STATUSES else STATUS_OPEN
        self.created_at = created_at or _now()
        self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "source": self.source,
            "evidence": self.evidence,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(
            severity=d.get("severity", SEVERITY_INFO),
            category=d.get("category", ""),
            title=d.get("title", ""),
            detail=d.get("detail", ""),
            source=d.get("source", ""),
            evidence=d.get("evidence", {}),
            status=d.get("status", STATUS_OPEN),
            finding_id=d.get("id"),
            created_at=d.get("created_at"),
        )

    def __repr__(self) -> str:
        return f"<Finding {self.id} {self.severity}/{self.status} {self.title[:40]}>"


def _ensure_dir():
    os.makedirs(_store_dir(), exist_ok=True)


def add_finding(finding: Finding) -> str:
    _ensure_dir()
    with _lock:
        try:
            with open(_findings_path(), "a") as f:
                f.write(json.dumps(finding.to_dict()) + "\n")
        except OSError:
            pass
    return finding.id


def list_findings(status: str | None = None, limit: int = 100) -> list[dict]:
    _ensure_dir()
    if not os.path.exists(_findings_path()):
        return []
    out = []
    try:
        with open(_findings_path()) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if status is not None and d.get("status") != status:
                    continue
                out.append(d)
    except OSError:
        return []
    return out[-limit:]


def get_finding(finding_id: str) -> dict | None:
    for d in list_findings(limit=100000):
        if d.get("id") == finding_id:
            return d
    return None


def update_finding_status(finding_id: str, status: str) -> bool:
    if status not in VALID_STATUSES:
        return False
    path = _findings_path()
    if not os.path.exists(path):
        return False
    changed = False
    with _lock:
        lines = []
        try:
            with open(path) as f:
                lines = f.readlines()
        except OSError:
            return False
        for i, line in enumerate(lines):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id") == finding_id:
                d["status"] = status
                d["updated_at"] = _now()
                lines[i] = json.dumps(d) + "\n"
                changed = True
                break
        if changed:
            try:
                with open(path, "w") as f:
                    f.writelines(lines)
            except OSError:
                return False
    return changed


def add_run(record: dict) -> None:
    _ensure_dir()
    with _lock:
        try:
            with open(_runs_path(), "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass


def list_runs(limit: int = 10) -> list[dict]:
    _ensure_dir()
    if not os.path.exists(_runs_path()):
        return []
    out = []
    try:
        with open(_runs_path()) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out[-limit:]
