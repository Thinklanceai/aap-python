"""
AAP Test Suite — Core compliance tests.

Tests verify conformance with AAP-0001 specification.
"""

import hashlib
import json
import pytest
from aap.core import AgentAction, Decision, SessionChain
from aap.utils import hash_payload, hash_context, hash_prompt, redact


class TestAgentActionRequired:
    """Section 5.1 — Required fields."""

    def test_required_fields_present(self):
        action = AgentAction(
            session_id="sess_001",
            actor="test-agent",
            decision=Decision.INVOKE_TOOL,
            context_hash=hash_context({"test": True}),
        ).seal()

        assert action.action_id is not None
        assert action.session_id == "sess_001"
        assert action.actor == "test-agent"
        assert action.decision == Decision.INVOKE_TOOL
        assert action.timestamp is not None
        assert action.context_hash is not None
        assert action.hash_self is not None

    def test_hash_prev_null_by_default(self):
        action = AgentAction(
            session_id="sess_001",
            actor="agent",
            decision=Decision.INTERNAL_REASONING,
            context_hash="abc123",
        ).seal()
        assert action.hash_prev is None


class TestDecisionTypes:
    """Section 8 — Decision model."""

    def test_all_decision_types_valid(self):
        decisions = [
            Decision.INVOKE_TOOL,
            Decision.DELEGATE,
            Decision.ROUTE,
            Decision.INTERNAL_REASONING,
            Decision.ABORT,
            Decision.COMPLETE,
        ]
        for decision in decisions:
            action = AgentAction(
                session_id="sess_001",
                actor="agent",
                decision=decision,
                context_hash="abc123",
            ).seal()
            assert action.decision == decision

    def test_abort_is_first_class_decision(self):
        """AAP-0001 Section 8: abort MUST be recordable."""
        action = AgentAction(
            session_id="sess_001",
            actor="agent",
            decision=Decision.ABORT,
            context_hash="abc123",
            intent_metadata={"reason": "policy_violation"},
        ).seal()
        assert action.decision == Decision.ABORT
        assert action.hash_self is not None


class TestCanonicalSerialization:
    """Section 6 — Canonical serialization."""

    def test_deterministic_hashing(self):
        """Same action must produce same hash every time."""
        kwargs = dict(
            session_id="sess_001",
            actor="agent",
            decision=Decision.INVOKE_TOOL,
            context_hash="ctx_hash",
            tool="send_email",
        )
        a1 = AgentAction(**kwargs)
        a1.action_id = "fixed-uuid"
        a1.timestamp = "2026-01-01T00:00:00+00:00"
        a1.seal()

        a2 = AgentAction(**kwargs)
        a2.action_id = "fixed-uuid"
        a2.timestamp = "2026-01-01T00:00:00+00:00"
        a2.seal()

        assert a1.hash_self == a2.hash_self

    def test_hash_changes_on_mutation(self):
        """Mutating a field and re-sealing must change the hash."""
        action = AgentAction(
            session_id="sess_001",
            actor="agent",
            decision=Decision.INVOKE_TOOL,
            context_hash="ctx_hash",
        )
        action.action_id = "fixed-uuid"
        action.timestamp = "2026-01-01T00:00:00+00:00"
        action.seal()
        original_hash = action.hash_self

        action.tool = "delete_file"
        action.hash_self = None
        action.seal()

        assert action.hash_self != original_hash

    def test_verify_detects_tampering(self):
        action = AgentAction(
            session_id="sess_001",
            actor="agent",
            decision=Decision.INVOKE_TOOL,
            context_hash="ctx_hash",
        ).seal()

        assert action.verify() is True

        # Tamper with the action after sealing
        action.tool = "malicious_tool"
        assert action.verify() is False


class TestChainIntegrity:
    """Section 7 — Chain integrity model."""

    def test_chain_links_correctly(self):
        chain = SessionChain(session_id="sess_test")

        a1 = chain.add(AgentAction(
            session_id="sess_test",
            actor="agent",
            decision=Decision.INTERNAL_REASONING,
            context_hash="ctx1",
        ))
        a2 = chain.add(AgentAction(
            session_id="sess_test",
            actor="agent",
            decision=Decision.INVOKE_TOOL,
            context_hash="ctx2",
            tool="search",
        ))

        assert a1.hash_prev is None
        assert a2.hash_prev == a1.hash_self

    def test_chain_verify_intact(self):
        chain = SessionChain(session_id="sess_test")
        for i in range(5):
            chain.add(AgentAction(
                session_id="sess_test",
                actor="agent",
                decision=Decision.INVOKE_TOOL,
                context_hash=f"ctx_{i}",
                tool=f"tool_{i}",
            ))

        is_valid, issues = chain.verify()
        assert is_valid is True
        assert len(issues) == 0

    def test_chain_detects_tampering(self):
        chain = SessionChain(session_id="sess_test")
        for i in range(3):
            chain.add(AgentAction(
                session_id="sess_test",
                actor="agent",
                decision=Decision.INVOKE_TOOL,
                context_hash=f"ctx_{i}",
            ))

        # Tamper with middle action
        chain._actions[1].tool = "hacked_tool"

        is_valid, issues = chain.verify()
        assert is_valid is False
        assert any(issue["index"] == 1 for issue in issues)

    def test_session_id_mismatch_raises(self):
        chain = SessionChain(session_id="sess_A")
        with pytest.raises(ValueError, match="session_id"):
            chain.add(AgentAction(
                session_id="sess_B",
                actor="agent",
                decision=Decision.COMPLETE,
                context_hash="ctx",
            ))

    def test_jsonl_export_parseable(self):
        chain = SessionChain(session_id="sess_test")
        chain.add(AgentAction(
            session_id="sess_test",
            actor="agent",
            decision=Decision.COMPLETE,
            context_hash="ctx",
        ))
        jsonl = chain.to_jsonl()
        parsed = json.loads(jsonl)
        assert parsed["session_id"] == "sess_test"


class TestPrivacyBoundaries:
    """Section 9 — Privacy and compliance boundaries."""

    def test_hash_payload_consistent(self):
        data = {"key": "value", "number": 42}
        h1 = hash_payload(data)
        h2 = hash_payload(data)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_redact_replaces_sensitive_keys(self):
        data = {"name": "John Doe", "amount": 50000, "public": "safe"}
        redacted = redact(data, sensitive_keys=["name", "amount"])
        assert redacted["public"] == "safe"
        assert "John Doe" not in str(redacted)
        assert "50000" not in str(redacted)
        assert redacted["name"].startswith("[REDACTED:")
        assert redacted["amount"].startswith("[REDACTED:")

    def test_action_does_not_store_raw_params(self):
        """
        Verify that AgentAction has no field for raw parameters.
        Only parameters_hash is allowed per AAP-0001 Section 12.
        """
        action = AgentAction(
            session_id="sess_001",
            actor="agent",
            decision=Decision.INVOKE_TOOL,
            context_hash="ctx",
        )
        assert not hasattr(action, "parameters"), \
            "AgentAction MUST NOT have a 'parameters' field — use parameters_hash"
        assert not hasattr(action, "result"), \
            "AgentAction MUST NOT have a 'result' field — use result_hash"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
