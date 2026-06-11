"""Normalização e tokenização de texto livre dos tickets."""

import re
from typing import Iterable

STOP_WORDS: frozenset[str] = frozenset(
    {
        "de", "da", "do", "em", "para", "com", "por", "que", "uma", "um",
        "não", "se", "no", "na", "o", "a", "os", "as", "e", "é", "ao",
        "como", "quando", "mais", "esse", "esta", "estes", "estas",
        "isso", "também", "ser", "está", "estão", "foi", "são", "ter",
        "tem", "the", "to", "of", "in", "and", "how", "can", "i", "my",
        "is", "it", "for", "not", "this", "that", "with", "but", "or",
    }
)

_TOKEN_RE = re.compile(r"[a-záéíóúãõâêîôûàèìòùç]{3,}")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str | None, max_length: int | None = None) -> str:
    if not text:
        return ""
    cleaned = _WHITESPACE_RE.sub(" ", text.replace("\r", " ").replace("\t", " ")).strip()
    if max_length is not None and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def tokenize(text: str, stop_words: Iterable[str] = STOP_WORDS) -> list[str]:
    if not text:
        return []
    stops = set(stop_words)
    words = _TOKEN_RE.findall(text.lower())
    return [w for w in words if w not in stops]
