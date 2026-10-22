import tiktoken
from typing import Optional

# Cache encodings
_ENCODINGS = {}


def get_encoding(model: str):
    if model in _ENCODINGS:
        return _ENCODINGS[model]
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    _ENCODINGS[model] = enc
    return enc


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    if not text:
        return 0
    enc = get_encoding(model)
    return len(enc.encode(text))


def count_messages_tokens(messages: list, model: str = "gpt-4o") -> int:
    """OpenAI-style message token estimation (approx)."""
    total = 0
    for m in messages or []:
        total += 4  # per-message overhead
        content = m.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += count_tokens(part.get("text", ""), model)
        role = m.get("role", "")
        total += count_tokens(role, model)
    total += 2  # priming
    return total


def bpe_compress_estimate(text: str, model: str = "gpt-4o") -> dict:
    """Return BPE token count + a naive compression ratio vs char/4 heuristic."""
    if not text:
        return {"chars": 0, "bpe_tokens": 0, "heuristic_tokens": 0, "ratio": 1.0}
    bpe = count_tokens(text, model)
    heuristic = max(1, len(text) // 4)
    ratio = round(bpe / heuristic, 4) if heuristic else 1.0
    return {
        "chars": len(text),
        "bpe_tokens": bpe,
        "heuristic_tokens": heuristic,
        "ratio": ratio,
    }


def dynamic_allocate(total_budget: int, prompt_tokens: int, completion_cap: int) -> dict:
    """Dynamic token allocation: given budget, prompt usage, and a desired completion cap."""
    remaining = max(0, total_budget - prompt_tokens)
    completion = min(completion_cap, remaining)
    return {
        "total_budget": total_budget,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion,
        "remaining": remaining - completion,
    }
