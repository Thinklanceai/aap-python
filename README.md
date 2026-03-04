# Agent Action Protocol (AAP)

**AAP defines the standard for verifiable AI agent actions.**

---

```bash
pip install aap-python
```

---

## The Problem

Autonomous AI agents now invoke tools, delegate to sub-agents, and modify external systems.

There is no standard for:
- What a verifiable agent action looks like
- How to chain actions with cryptographic integrity
- What can and cannot be stored (privacy boundaries)
- How to verify a session was not tampered with

Every framework invents its own logging. None are interoperable.

## What AAP Is

AAP is a **minimal, framework-agnostic data standard** for representing agent actions.

It specifies:
- A canonical `AgentAction` data model
- A cryptographic chain integrity model
- Explicit privacy boundaries (no raw reasoning storage)
- An extensibility mechanism for framework-specific metadata

AAP is **not** a policy engine. Not a certification body. Not a SaaS.

It is a primitive. The smallest possible unit of verifiable agent cognition.

## Quickstart

```python
from aap.core import AgentAction, Decision, SessionChain
from aap.utils import hash_context, hash_payload

# Create a session
chain = SessionChain()

# Record an action
action = chain.add(AgentAction(
    session_id=chain.session_id,
    actor="my-agent-v1",
    decision=Decision.INVOKE_TOOL,
    context_hash=hash_context({"user_request": "send report"}),
    tool="send_email",
    parameters_hash=hash_payload({"to": "alice@example.com"}),
))

# Abort is a first-class decision
abort = chain.add(AgentAction(
    session_id=chain.session_id,
    actor="my-agent-v1",
    decision=Decision.ABORT,
    context_hash=hash_context({"reason": "budget_exceeded"}),
    intent_metadata={"policy": "spend_limit"},
))

# Verify chain integrity
is_valid, issues = chain.verify()
print(f"Chain intact: {is_valid}")  # Chain intact: True

# Export as JSONL for audit
with open("session.jsonl", "w") as f:
    f.write(chain.to_jsonl())
```

## CLI Verification

```bash
# Verify a recorded session
aap verify session.jsonl

✓ 47 actions loaded
✓ Chain integrity: intact
✓ Session: 550e8400-e29b-41d4-a716-446655440000
```

## Decision Types

| Decision | When to use |
|----------|-------------|
| `invoke_tool` | Agent calls an external tool |
| `delegate` | Agent delegates to a sub-agent |
| `route` | Agent selects next step in workflow |
| `internal_reasoning` | Decision without external action |
| `abort` | Agent explicitly refuses an action |
| `complete` | Task completion |

`abort` is a **first-class decision**. Refusing to act is as important as acting.

## Privacy by Design

AAP explicitly prohibits storing:
- Raw chain-of-thought
- Unredacted prompts
- Raw parameters or results

Use the provided helpers:

```python
from aap.utils import hash_payload, hash_prompt, redact

# Hash before storing
params_hash = hash_payload({"amount": 50000, "to": "alice"})
prompt_hash = hash_prompt("Transfer $50,000 to external account")

# Redact sensitive fields
safe_metadata = redact(metadata, sensitive_keys=["name", "amount"])
```

## Framework Integrations

### LangChain

```python
from aap.integrations.langchain import AAPCallbackHandler

chain = SessionChain()
handler = AAPCallbackHandler(session_chain=chain, actor="my-agent")
agent.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### OpenAI Agents SDK

```python
from aap.integrations.openai import wrap_tool

chain = SessionChain()

@wrap_tool(chain=chain, actor="my-agent")
def search_web(query: str) -> str:
    return do_search(query)
```

## The Specification

The normative specification is [AAP-0001.md](./AAP-0001.md).

This implementation is the reference implementation. It is informative, not normative.

## Contributing

AAP is an open standard. All decisions are made in public.

- Open an issue to propose changes to the spec
- Submit a PR for the reference implementation
- See [CONTRIBUTING.md](./CONTRIBUTING.md)

## License

Apache 2.0 — use freely, in any product, open or closed.

---

*"There is no standard for verifiable AI agent actions. AAP is that standard."*
