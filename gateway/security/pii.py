import re
from typing import Any, Dict

# PII patterns (regex-based, lightweight; production should use NER models)
PII_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone_cn": re.compile(r"\b1[3-9]\d{9}\b"),
    "phone_intl": re.compile(r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"),
    "id_card_cn": re.compile(r"\b\d{17}[\dXx]\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


def mask_pii_text(text: str, mask_char: str = "*") -> str:
    if not text:
        return text
    out = text
    for name, pat in PII_PATTERNS.items():
        def repl(m):
            s = m.group(0)
            if len(s) <= 4:
                return mask_char * len(s)
            return s[:2] + mask_char * (len(s) - 4) + s[-2:]
        out = pat.sub(repl, out)
    return out


def mask_pii_obj(obj: Any, mask_char: str = "*") -> Any:
    if isinstance(obj, str):
        return mask_pii_text(obj, mask_char)
    if isinstance(obj, dict):
        return {k: mask_pii_obj(v, mask_char) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_pii_obj(x, mask_char) for x in obj]
    return obj


def pii_stats(text: str) -> Dict[str, int]:
    stats = {}
    for name, pat in PII_PATTERNS.items():
        stats[name] = len(pat.findall(text))
    return stats
