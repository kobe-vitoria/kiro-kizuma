"""Scraper do GitBook público da Kobe.

Baixa todas as páginas listadas no `/sitemap.xml` do GitBook, quebra cada
uma em chunks por heading, e salva como JSON pra ser consumido pelo
retrieval (issue #3). Esse módulo NÃO toca o pipeline de geração.
"""

import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

from kiro.domain.models import GitBookChunk

log = logging.getLogger(__name__)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _parse_sitemap(content: str, base_url: str) -> list[str]:
    """Parse sitemap XML, retorna URLs únicas que começam com base_url.

    Levanta ValueError se o XML for inválido ou se nenhuma URL casar
    com base_url (provavelmente erro de configuração).
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"sitemap XML inválido: {e}") from e

    base_normalized = base_url.rstrip("/")
    seen: set[str] = set()
    urls: list[str] = []
    for loc in root.iterfind(".//sm:url/sm:loc", _SITEMAP_NS):
        url = (loc.text or "").strip()
        if not url:
            continue
        if url != base_normalized and not url.startswith(base_normalized + "/"):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    if not urls:
        raise ValueError(
            f"sitemap não retornou nenhuma URL começando com {base_url!r}"
        )
    return urls


def _find_content_container(soup: BeautifulSoup) -> Optional[Tag]:
    """Acha o container principal de conteúdo da página GitBook.

    Tenta na ordem: <main>, [data-testid='page.contentEditor'], <article>.
    Retorna None se nada bater (chamador trata como falha de parse).
    """
    main = soup.find("main")
    if main:
        return main
    testid = soup.find(attrs={"data-testid": "page.contentEditor"})
    if testid:
        return testid
    article = soup.find("article")
    if article:
        return article
    return None


def _extract_page_title(soup: BeautifulSoup) -> str:
    """Título da página: primeiro <h1> do <body>, ou <title> como fallback.

    Escopo restrito ao <body> evita pegar <h1> stale/SEO injetado no <head>.
    """
    body = soup.body or soup
    h1 = body.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    title = soup.find("title")
    if title and title.get_text(strip=True):
        return title.get_text(strip=True)
    return "(sem título)"


def _section_anchor(heading: Tag) -> str:
    """Anchor pra deep-link. Usa heading.id se presente, senão slugifica texto.

    Garante string não-vazia mesmo pra headings sem alfa-numéricos —
    cai pra 'section' como sentinel pra evitar fragment '#' quebrado.
    """
    if heading.get("id"):
        return heading["id"]
    return _slugify(heading.get_text(strip=True)) or "section"


def _slugify(text: str) -> str:
    """Slug ASCII simples: minúsculas, remove acentos, troca não-alfanum por '-'."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    lowered = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug


_HEADING_TAGS = {"h1", "h2", "h3"}

_CHUNK_MAX_CHARS = 1000
_CHUNK_TARGET_CHARS = 800


def _split_oversized(content: str) -> list[str]:
    """Divide texto > _CHUNK_MAX_CHARS em sub-chunks ≤ ~_CHUNK_TARGET_CHARS.

    Quebra preferencialmente em fim de parágrafo (\\n\\n). Se um parágrafo
    sozinho exceder o target, ele é mantido como sub-chunk único (fica
    acima de target mas abaixo de 2× target na prática). Sem quebra no
    meio de palavra.
    """
    if len(content) <= _CHUNK_MAX_CHARS:
        return [content]

    paragraphs = content.split("\n\n")
    sub_chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    for para in paragraphs:
        para_len = len(para)
        if buffer and buffer_len + 2 + para_len > _CHUNK_TARGET_CHARS:
            sub_chunks.append("\n\n".join(buffer))
            buffer = [para]
            buffer_len = para_len
        else:
            buffer.append(para)
            buffer_len += (2 if buffer_len else 0) + para_len

    if buffer:
        sub_chunks.append("\n\n".join(buffer))

    return sub_chunks


def _chunk_page(html: str, page_url: str) -> list[GitBookChunk]:
    """Quebra a página em chunks por heading (h1/h2/h3).

    Texto antes do primeiro heading é atribuído a uma "seção intro"
    com title = page_title. Seções pequenas (<200 chars) também são
    preservadas — info curta é útil pro retrieval.

    Seções grandes (>_CHUNK_MAX_CHARS) são sub-divididas por
    _split_oversized em sub-chunks de ~_CHUNK_TARGET_CHARS chars,
    preservando section_title e section_anchor em cada sub-chunk.

    Retorna lista vazia se container principal não for encontrado.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = _find_content_container(soup)
    if container is None:
        return []

    page_title = _extract_page_title(soup)

    # Coleta (section_title, section_anchor, [paragraphs]) em ordem
    sections: list[tuple[str, str, list[str]]] = []
    current_title = page_title
    current_anchor = _slugify(page_title)
    current_paragraphs: list[str] = []

    for element in container.descendants:
        if not isinstance(element, Tag):
            continue

        if element.name in _HEADING_TAGS:
            # Skip nested headings (e.g., <h3> inside <h2>) — outer já abriu seção
            other_headings = _HEADING_TAGS - {element.name}
            if element.find_parent(other_headings):
                continue
            # Fecha a seção atual antes de abrir a nova
            if current_paragraphs:
                sections.append((current_title, current_anchor, current_paragraphs))
            current_title = element.get_text(strip=True) or "(sem título)"
            current_anchor = _section_anchor(element)
            current_paragraphs = []
            continue

        if element.name in {"p", "li"}:
            # Skip <p>/<li> dentro de heading, <li> ou <p> — texto já capturado
            # pelo ancestor (evita duplicar conteúdo em listas aninhadas e
            # parágrafos dentro de itens de lista)
            if element.find_parent(_HEADING_TAGS | {"p", "li"}):
                continue
            text = element.get_text(separator=" ", strip=True)
            if text:
                current_paragraphs.append(text)

    # Fecha última seção
    if current_paragraphs:
        sections.append((current_title, current_anchor, current_paragraphs))

    # Materializa chunks, sub-dividindo seções > _CHUNK_MAX_CHARS
    chunks: list[GitBookChunk] = []
    for title, anchor, paragraphs in sections:
        content = "\n\n".join(paragraphs).strip()
        if not content:
            continue
        for sub_content in _split_oversized(content):
            chunks.append(
                GitBookChunk(
                    page_title=page_title,
                    page_url=page_url,
                    section_title=title,
                    section_anchor=anchor,
                    content=sub_content,
                )
            )
    return chunks
