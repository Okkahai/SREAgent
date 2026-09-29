"""Deterministic action policy (docs/08 §3). Pure and table-driven: the model proposes an action
type, this table alone decides its risk and whether OpsPilot may ever execute it. The LLM never
writes `risk`."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Risk(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    HIGH = "HIGH"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass(frozen=True)
class Rule:
    risk: Risk
    executable: bool  # can OpsPilot itself run it (after approval)?
    note: str


RULES: dict[str, Rule] = {
    "OPEN_PR": Rule(Risk.LOW, True, "creates a branch and pull request; never merges"),
    "RUNBOOK": Rule(Risk.READ_ONLY, False, "instructions for a human"),
    "ROLLBACK": Rule(Risk.HIGH, False, "runbook only: a human performs the rollback"),
    "RESTART": Rule(Risk.HIGH, False, "runbook only: a human restarts the service"),
    "SCALE": Rule(Risk.HIGH, False, "runbook only: a human scales the service"),
    "CONFIG_CHANGE": Rule(Risk.HIGH, False, "runbook only: a human changes the config"),
    "MERGE_PR": Rule(Risk.DESTRUCTIVE, False, "not executable by OpsPilot"),
    "DB_OPERATION": Rule(Risk.DESTRUCTIVE, False, "not executable by OpsPilot"),
    "INFRA_CHANGE": Rule(Risk.DESTRUCTIVE, False, "not executable by OpsPilot"),
}
PROPOSABLE = frozenset(RULES) - {"MERGE_PR", "DB_OPERATION", "INFRA_CHANGE"}

# Files an automated PR may never touch, whatever the model asks for.
PROTECTED_PREFIXES = (".github/", ".git/")
PROTECTED_NAMES = ("CODEOWNERS", ".env", "id_rsa")
MAX_FILES = 5
MAX_FILE_BYTES = 20_000


@dataclass
class Decision:
    risk: str
    requires_approval: bool
    executable: bool
    approver_role: str = "approver"
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def decide(action_type: str) -> Decision:
    rule = RULES.get(action_type)
    if rule is None:
        return Decision(
            Risk.DESTRUCTIVE, True, False, reasons=[f"unknown action type {action_type!r}"]
        )
    return Decision(
        rule.risk,
        rule.risk != Risk.READ_ONLY,
        rule.executable,
        reasons=[rule.note],
    )


def validate_parameters(action_type: str, params: dict[str, object]) -> list[str]:
    """Problems that make a proposal unacceptable regardless of approval."""
    if action_type != "OPEN_PR":
        return []
    problems: list[str] = []
    files = params.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        return [f"OPEN_PR needs 1-{MAX_FILES} files"]
    for f in files:
        path, content = (f.get("path"), f.get("content")) if isinstance(f, dict) else (None, None)
        if not isinstance(path, str) or not isinstance(content, str):
            problems.append("file entries need string path and content")
            continue
        parts = path.split("/")
        if path.startswith("/") or ".." in parts:
            problems.append(f"unsafe path {path!r}")
        elif path.startswith(PROTECTED_PREFIXES) or parts[-1] in PROTECTED_NAMES:
            problems.append(f"protected path {path!r}")
        if len(content.encode()) > MAX_FILE_BYTES:
            problems.append(f"{path!r} exceeds {MAX_FILE_BYTES} bytes")
    return problems
