"""Atlassian Document Format → texto plano. Robusto a entradas malformadas."""

from typing import Any


def extract_text_from_adf(node: Any) -> str:
    """Percorre recursivamente o ADF e retorna texto concatenado.

    Aceita None, strings, dicts e estruturas aninhadas.
    Retorna string vazia para entradas inesperadas.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    parts: list[str] = []
    if node.get("type") == "text":
        text_value = node.get("text", "")
        if text_value:
            parts.append(text_value)

    for child in node.get("content") or []:
        sub = extract_text_from_adf(child)
        if sub:
            parts.append(sub)

    return " ".join(parts).strip()
