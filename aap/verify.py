#!/usr/bin/env python3
"""
aap verify — CLI integrity checker for AAP session chains.

Usage:
    aap verify session.jsonl
    cat session.jsonl | aap verify -

Output:
    ✓ 47 actions verified
    ✓ Chain integrity: intact

    or

    ✗ Chain integrity: FAILED
    Issue at action 23 (id=a3f1b2...): hash_self mismatch
"""

import json
import sys
import hashlib
from pathlib import Path


def load_actions(source: str) -> list[dict]:
    if source == "-":
        lines = sys.stdin.read().strip().splitlines()
    else:
        lines = Path(source).read_text().strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def verify_action_hash(action: dict) -> bool:
    """Recompute hash_self and compare."""
    stored_hash = action.get("hash_self")
    if not stored_hash:
        return False

    # Build canonical dict excluding hash_self
    d = {k: v for k, v in action.items() if k != "hash_self" and v is not None}
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return computed == stored_hash


def verify_chain(actions: list[dict]) -> tuple[bool, list[dict]]:
    issues = []

    for i, action in enumerate(actions):
        action_id = action.get("action_id", "unknown")[:8]

        # Verify hash_self
        if not verify_action_hash(action):
            issues.append({
                "index": i,
                "action_id": action_id,
                "error": "hash_self mismatch — action may have been tampered with",
            })

        # Verify chain linkage
        if i == 0:
            if action.get("hash_prev") is not None:
                issues.append({
                    "index": i,
                    "action_id": action_id,
                    "error": "first action hash_prev should be null",
                })
        else:
            expected_prev = actions[i - 1].get("hash_self")
            if action.get("hash_prev") != expected_prev:
                issues.append({
                    "index": i,
                    "action_id": action_id,
                    "error": f"chain break — hash_prev mismatch",
                })

    return len(issues) == 0, issues


def main():
    if len(sys.argv) < 2:
        print("Usage: aap verify <session.jsonl | ->")
        sys.exit(1)

    source = sys.argv[1]

    try:
        actions = load_actions(source)
    except Exception as e:
        print(f"✗ Failed to load: {e}")
        sys.exit(1)

    if not actions:
        print("✗ No actions found in input")
        sys.exit(1)

    is_valid, issues = verify_chain(actions)

    print(f"{'✓' if is_valid else '✗'} {len(actions)} actions loaded")

    if is_valid:
        print(f"✓ Chain integrity: intact")
        print(f"✓ Session: {actions[0].get('session_id', 'unknown')}")
        sys.exit(0)
    else:
        print(f"✗ Chain integrity: FAILED — {len(issues)} issue(s) found\n")
        for issue in issues:
            print(f"  Issue at position {issue['index']} (id={issue['action_id']}...):")
            print(f"  → {issue['error']}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
