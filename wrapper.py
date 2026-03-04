"""
AAP OpenAI Agents SDK Integration

Wraps OpenAI tool calls to produce AAP-compliant AgentAction records.

Usage:
    from aap.integrations.openai import wrap_tool
    from aap.core import SessionChain

    chain = SessionChain()

    @wrap_tool(chain=chain, actor="my-openai-agent")
    def my_tool(param: str) -> str:
        return do_something(param)
"""

import functools
from aap.core import AgentAction, Decision, SessionChain
from aap.utils import hash_payload, hash_context


def wrap_tool(chain: SessionChain, actor: str):
    """
    Decorator that wraps any callable tool to record
    AAP-compliant actions on every invocation.

    Records:
    - invoke_tool on call
    - result_hash on success
    - abort on exception
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tool_name = func.__name__

            # Record invocation
            action = AgentAction(
                session_id=chain.session_id,
                actor=actor,
                decision=Decision.INVOKE_TOOL,
                context_hash=hash_context({"tool": tool_name}),
                tool=tool_name,
                parameters_hash=hash_payload({"args": args, "kwargs": kwargs}),
            )
            chain.add(action)

            try:
                result = func(*args, **kwargs)
                # Update with result hash
                action.result_hash = hash_payload(result)
                action.hash_self = None
                action.seal()
                return result

            except Exception as e:
                # Record abort on failure
                abort_action = AgentAction(
                    session_id=chain.session_id,
                    actor=actor,
                    decision=Decision.ABORT,
                    context_hash=hash_context({"tool": tool_name, "error": type(e).__name__}),
                    tool=tool_name,
                    intent_metadata={"error_type": type(e).__name__},
                )
                chain.add(abort_action)
                raise

        return wrapper
    return decorator


def record_decision(
    chain: SessionChain,
    actor: str,
    decision: Decision,
    context: dict,
    **kwargs,
) -> AgentAction:
    """
    Manually record any decision into the chain.
    Use this for routing, delegation, or reasoning decisions
    that aren't tool calls.
    """
    action = AgentAction(
        session_id=chain.session_id,
        actor=actor,
        decision=decision,
        context_hash=hash_context(context),
        **kwargs,
    )
    return chain.add(action)
