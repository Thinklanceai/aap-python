"""
AAP LangChain Integration

Wraps LangChain tool calls to produce AAP-compliant AgentAction records.

Usage:
    from aap.integrations.langchain import AAPCallbackHandler
    from aap.core import SessionChain

    chain = SessionChain()
    handler = AAPCallbackHandler(session_chain=chain, actor="my-agent")

    # Pass handler to any LangChain agent or chain
    agent.invoke({"input": "..."}, config={"callbacks": [handler]})

    # Export verified JSONL
    print(chain.to_jsonl())
"""

from aap.core import AgentAction, Decision, SessionChain
from aap.utils import hash_payload, hash_context

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
    LANGCHAIN_AVAILABLE = True
except ImportError:
    # Graceful degradation if langchain not installed
    BaseCallbackHandler = object
    LANGCHAIN_AVAILABLE = False


class AAPCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that records agent actions
    as AAP-compliant AgentAction records.

    Captures:
    - Tool invocations (invoke_tool)
    - Tool errors (abort)
    - Agent actions (route, delegate)
    - LLM decisions (internal_reasoning)
    """

    def __init__(self, session_chain: SessionChain, actor: str):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-core is required for AAPCallbackHandler. "
                "Install with: pip install langchain-core"
            )
        self.chain = session_chain
        self.actor = actor

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        tool_name = serialized.get("name", "unknown_tool")
        action = AgentAction(
            session_id=self.chain.session_id,
            actor=self.actor,
            decision=Decision.INVOKE_TOOL,
            context_hash=hash_context({"tool": tool_name}),
            tool=tool_name,
            parameters_hash=hash_payload(input_str),
            extension={
                "langchain.run_id": str(kwargs.get("run_id", "")),
            },
        )
        self.chain.add(action)

    def on_tool_end(self, output: str, **kwargs):
        # Record result hash on most recent tool action
        if self.chain._actions:
            last = self.chain._actions[-1]
            if last.decision == Decision.INVOKE_TOOL:
                last.result_hash = hash_payload(output)
                # Re-seal with result hash
                last.hash_self = None
                last.seal()

    def on_tool_error(self, error: Exception, **kwargs):
        action = AgentAction(
            session_id=self.chain.session_id,
            actor=self.actor,
            decision=Decision.ABORT,
            context_hash=hash_context({"error": type(error).__name__}),
            intent_metadata={"error_type": type(error).__name__},
        )
        self.chain.add(action)

    def on_agent_action(self, action, **kwargs):
        aap_action = AgentAction(
            session_id=self.chain.session_id,
            actor=self.actor,
            decision=Decision.ROUTE,
            context_hash=hash_context({"action": str(action)}),
            intent_metadata={"log": action.log[:200] if hasattr(action, "log") else None},
        )
        self.chain.add(aap_action)

    def on_agent_finish(self, finish, **kwargs):
        action = AgentAction(
            session_id=self.chain.session_id,
            actor=self.actor,
            decision=Decision.COMPLETE,
            context_hash=hash_context({"finish": "agent_finish"}),
        )
        self.chain.add(action)
