"""
AAP Utilities — Hashing and redaction helpers.

Per AAP-0001 Section 12: raw parameters and results
MUST NOT be stored. Use these helpers to hash before persisting.
"""

import hashlib
import json
from typing import Any


def hash_payload(payload: Any) -> str:
    """
    Hash any payload (dict, string, etc.) for safe storage.
    Use this for parameters, results, and context snapshots.

    Returns SHA256 hex string.
    """
    if isinstance(payload, (dict, list)):
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif isinstance(payload, str):
        serialized = payload
    else:
        serialized = str(payload)

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_context(context: dict) -> str:
    """
    Hash a context snapshot for the context_hash required field.
    The raw context should be stored separately with appropriate access controls.
    """
    return hash_payload(context)


def hash_prompt(prompt: str) -> str:
    """
    Hash a prompt string.
    Per AAP-0001 Section 9.1: raw prompts MUST NOT be persisted without consent.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def redact(data: dict, sensitive_keys: list[str]) -> dict:
    """
    Redact sensitive keys from a dict before storing in intent_metadata.
    Replaces values with their SHA256 hash.
    """
    result = {}
    for k, v in data.items():
        if k in sensitive_keys:
            result[k] = f"[REDACTED:{hash_payload(v)[:8]}]"
        else:
            result[k] = v
    return result
