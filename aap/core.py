"""
Agent Action Protocol (AAP) — Core Implementation
Reference implementation for AAP-0001.

This implementation is informative, not normative.
Conformance is defined by the AAP-0001 specification.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Decision(str, Enum):
    """
    AAP-0001 Section 8 — Canonical decision types.
    All decisions are first-class: including abort.
    """
    INVOKE_TOOL = "invoke_tool"
    DELEGATE = "delegate"
    ROUTE = "route"
    INTERNAL_REASONING = "internal_reasoning"
    ABORT = "abort"
    COMPLETE = "complete"


@dataclass
class AgentAction:
    """
    Canonical AAP AgentAction record.

    Required fields (AAP-0001 Section 5.1) are positional.
    Optional fields (AAP-0001 Section 5.2) default to None.

    IMPORTANT: Raw parameters and results MUST NOT be passed directly.
    Use aap.utils.hash_payload() before storing any sensitive data.
    """

    # --- Required fields ---
    session_id: str
    actor: str
    decision: Decision
    context_hash: str

    # --- Auto-generated required fields ---
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # --- Chain integrity ---
    hash_prev: Optional[str] = None  # null for first action in session

    # --- Optional fields ---
    tool: Optional[str] = None
    parameters_hash: Optional[str] = None   # hash only, never raw params
    result_hash: Optional[str] = None       # hash only, never raw result
    confidence_score: Optional[float] = None
    intent_metadata: Optional[dict] = None
    extension: Optional[dict] = None

    # --- Computed on seal() ---
    hash_self: Optional[str] = field(default=None, init=False)

    def _canonical_dict(self) -> dict:
        """
        Build a deterministic dict for hashing per AAP-0001 Section 6.
        Excludes hash_self (computed over all other fields).
        """
        d = {
            "action_id": self.action_id,
            "actor": self.actor,
            "context_hash": self.context_hash,
            "decision": self.decision.value if isinstance(self.decision, Decision) else self.decision,
            "hash_prev": self.hash_prev,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }
        # Include optional fields only if set
        if self.tool is not None:
            d["tool"] = self.tool
        if self.parameters_hash is not None:
            d["parameters_hash"] = self.parameters_hash
        if self.result_hash is not None:
            d["result_hash"] = self.result_hash
        if self.confidence_score is not None:
            d["confidence_score"] = self.confidence_score
        if self.intent_metadata is not None:
            d["intent_metadata"] = self.intent_metadata
        if self.extension is not None:
            d["extension"] = self.extension
        return d

    def _serialize_canonical(self) -> str:
        """
        AAP-0001 Section 6 canonical serialization:
        UTF-8, sorted keys, no whitespace.
        """
        return json.dumps(self._canonical_dict(), sort_keys=True, separators=(",", ":"))

    def seal(self) -> "AgentAction":
        """
        Compute and set hash_self.
        Call this once all fields are set.
        Returns self for chaining.
        """
        canonical = self._serialize_canonical()
        self.hash_self = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self

    def to_dict(self) -> dict:
        """Export full action including hash_self."""
        d = self._canonical_dict()
        d["hash_self"] = self.hash_self
        return d

    def to_json(self) -> str:
        """Export as canonical JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def verify(self) -> bool:
        """
        Verify this action's hash_self is consistent with its contents.
        Returns True if intact, False if tampered.
        """
        if self.hash_self is None:
            return False
        canonical = self._serialize_canonical()
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.hash_self == expected

    def __repr__(self) -> str:
        return (
            f"AgentAction(id={self.action_id[:8]}... "
            f"decision={self.decision} "
            f"actor={self.actor} "
            f"sealed={'yes' if self.hash_self else 'no'})"
        )


class SessionChain:
    """
    Manages a cryptographically linked chain of AgentActions
    within a single session. (AAP-0001 Section 7)
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self._actions: list[AgentAction] = []

    def add(self, action: AgentAction) -> AgentAction:
        """
        Append an action to the chain.
        Sets hash_prev automatically and seals the action.
        """
        if action.session_id != self.session_id:
            raise ValueError(
                f"Action session_id {action.session_id!r} "
                f"does not match chain session_id {self.session_id!r}"
            )

        # Link to previous action
        if self._actions:
            action.hash_prev = self._actions[-1].hash_self
        else:
            action.hash_prev = None

        action.seal()
        self._actions.append(action)
        return action

    def verify(self) -> tuple[bool, list[dict]]:
        """
        Verify the integrity of the entire chain.

        Returns:
            (is_valid: bool, issues: list of issue dicts)
        """
        issues = []

        for i, action in enumerate(self._actions):
            # Verify individual hash
            if not action.verify():
                issues.append({
                    "index": i,
                    "action_id": action.action_id,
                    "error": "hash_self mismatch — action may have been tampered with",
                })

            # Verify chain linkage
            if i == 0:
                if action.hash_prev is not None:
                    issues.append({
                        "index": i,
                        "action_id": action.action_id,
                        "error": "first action hash_prev should be null",
                    })
            else:
                expected_prev = self._actions[i - 1].hash_self
                if action.hash_prev != expected_prev:
                    issues.append({
                        "index": i,
                        "action_id": action.action_id,
                        "error": f"chain break — hash_prev mismatch at position {i}",
                    })

        return len(issues) == 0, issues

    def to_jsonl(self) -> str:
        """Export full chain as JSONL (one action per line)."""
        return "\n".join(a.to_json() for a in self._actions)

    def __len__(self) -> int:
        return len(self._actions)

    def __iter__(self):
        return iter(self._actions)
