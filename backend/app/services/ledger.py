"""Hash-linked, append-only record chain. Each entry hash = SHA-256(prev_hash || canonical payload).
Tamper-evident only: it cannot prove WHEN entries were written (no trusted timestamping) and
does not replace legally mandated evidence-handling procedures."""
import hashlib
import json

GENESIS = "0" * 64
DISCLAIMER = ("This chain is tamper-evident, not tamper-proof. It does not provide independent trusted "
              "timestamping and does not replace legally mandated chain-of-custody procedures.")


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(payload)).encode()).hexdigest()


def verify_chain(entries: list[dict]) -> dict:
    """entries: ordered dicts with keys payload, prev_hash, entry_hash, seq.
    Returns {valid, checked, first_broken_seq, reason}."""
    prev = GENESIS
    for e in entries:
        if e["prev_hash"] != prev:
            return {"valid": False, "checked": e["seq"], "first_broken_seq": e["seq"],
                    "reason": "prev_hash does not match preceding entry (entry removed, reordered or inserted)"}
        if compute_hash(prev, e["payload"]) != e["entry_hash"]:
            return {"valid": False, "checked": e["seq"], "first_broken_seq": e["seq"],
                    "reason": "entry content does not match its recorded hash (entry modified)"}
        prev = e["entry_hash"]
    return {"valid": True, "checked": len(entries), "first_broken_seq": None, "reason": "chain intact"}
