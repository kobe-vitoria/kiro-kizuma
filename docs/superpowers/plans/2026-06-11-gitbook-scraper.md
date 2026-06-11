# GitBook Public Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Baixar o GitBook público da Kobe e gerar um cache JSON com chunks por seção, pronto pra ser consumido pelo retrieval da issue #3.

**Architecture:** Função síncrona `scrape_public_gitbook(base_url, output_path)` em `kiro/infrastructure/gitbook_loader.py`. Descobre páginas via `sitemap.xml`, baixa cada uma com httpx+tenacity, parseia HTML com BeautifulSoup4, quebra por heading (h1/h2/h3) em chunks de 200-1000 chars, e grava JSON único versionado por `fetched_at`. CLI adiciona subcomando `kiro fetch-gitbook --public`.

**Tech Stack:** Python 3.11+, httpx, tenacity, beautifulsoup4 (novo), pydantic v2, pydantic-settings, pytest, respx (dev-only, novo).

**Branch:** `feature/gitbook-scraper` (já criada a partir de `main`, com o spec commitado em `0315d62`).

**Spec:** `docs/superpowers/specs/2026-06-11-gitbook-scraper-design.md`.

**Issue:** [#2](https://github.com/kobe-matheussilva/KIRO/issues/2).

---

## File Structure

| Arquivo | Cria/Modifica | Responsabilidade |
|---------|---------------|------------------|
| `requirements.txt` | Modifica | +`beautifulsoup4` |
| `requirements-dev.txt` | Modifica | +`respx` |
| `.gitignore` | Modifica | +`kiro/data/*_cache.json` |
| `.env.example` | Modifica | +3 vars do GitBook |
| `kiro/data/.gitkeep` | Cria | Reserva diretório no clone |
| `kiro/config/settings.py` | Modifica | +3 settings: `gitbook_public_url`, `gitbook_cache_path`, `gitbook_request_delay_seconds` |
| `kiro/domain/models.py` | Modifica | +`GitBookChunk` e `ScrapingResult` dataclasses |
| `kiro/infrastructure/gitbook_loader.py` | Cria | Núcleo: discovery + fetch + parse + chunk + persistence |
| `kiro/interfaces/cli.py` | Modifica | +subcomando `fetch-gitbook` |
| `tests/conftest.py` | Modifica | Limpa env vars do GitBook entre testes |
| `tests/test_settings.py` | Modifica | +1 teste pra default da URL |
| `tests/test_gitbook_loader.py` | Cria | 9 testes (unidade + integração com respx) |
| `tests/test_cli.py` | Cria | 1 teste de dispatch do subcomando |

`GitBookChunk` e `ScrapingResult` ficam em `kiro/domain/models.py` (não no `gitbook_loader.py` como o spec sugere) pra ser consistente com `Ticket` que já vive lá. Issue #3 vai precisar importar `GitBookChunk` do domain.

---

## Task 1: Dependências + scaffolding (sem testes)

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `.gitignore`
- Modify: `.env.example`
- Create: `kiro/data/.gitkeep`

- [ ] **Step 1: Adicionar `beautifulsoup4` ao `requirements.txt`**

Estado atual:
```
httpx>=0.27,<1.0
pydantic>=2.6,<3.0
pydantic-settings>=2.2,<3.0
tenacity>=8.2,<10.0
python-docx>=1.1,<2.0
```

Adicionar uma linha:
```
beautifulsoup4>=4.12,<5.0
```

- [ ] **Step 2: Adicionar `respx` ao `requirements-dev.txt`**

Estado atual:
```
-r requirements.txt
pytest>=8.0
pytest-cov>=4.1
```

Adicionar uma linha:
```
respx>=0.21,<1.0
```

- [ ] **Step 3: Atualizar `.gitignore`**

Adicionar antes da última linha:
```
# GitBook cache (regenerado por `kiro fetch-gitbook`)
kiro/data/*_cache.json
```

- [ ] **Step 4: Criar diretório `kiro/data/` com `.gitkeep`**

```bash
mkdir -p kiro/data
touch kiro/data/.gitkeep
```

- [ ] **Step 5: Atualizar `.env.example`**

Adicionar bloco antes do bloco `# ─── Pipeline ───`:

```
# ─── GitBook RAG (opcional — habilita cache local de docs) ──────────
# URL pública da GitBook. O scraper lê /sitemap.xml a partir daqui.
GITBOOK_PUBLIC_URL=https://kobeapps.gitbook.io/kobe.io-documentacao
GITBOOK_CACHE_PATH=kiro/data/gitbook_public_cache.json
# Pausa entre requisições pra ser educado com o servidor (segundos).
GITBOOK_REQUEST_DELAY_SECONDS=0.5
```

- [ ] **Step 6: Instalar dependências no venv**

Run: `source .venv/bin/activate && pip install -r requirements-dev.txt`
Expected: instala `beautifulsoup4`, `soupsieve` (transitiva) e `respx`.

- [ ] **Step 7: Confirmar que testes existentes continuam verdes**

Run: `.venv/bin/python -m pytest -q`
Expected: 57 passed.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore .env.example kiro/data/.gitkeep
git commit -m "chore(deps): adicionar beautifulsoup4 e respx para GitBook scraper

- requirements.txt: +beautifulsoup4 (parser HTML)
- requirements-dev.txt: +respx (mock httpx em testes)
- .gitignore: ignorar kiro/data/*_cache.json
- .env.example: +3 vars GITBOOK_*
- kiro/data/.gitkeep: reservar pasta no repo

Refs #2"
```

---

## Task 2: Settings — 3 campos novos (TDD)

**Files:**
- Modify: `kiro/config/settings.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Atualizar `tests/conftest.py`**

Encontrar a lista de keys em `_isolated_env` (linha ~9-17) e adicionar as 3 vars no fim da lista:

```python
"GITBOOK_PUBLIC_URL", "GITBOOK_CACHE_PATH", "GITBOOK_REQUEST_DELAY_SECONDS",
```

A lista final fica:
```python
for key in [
    "JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY",
    "JIRA_EXTRA_JQL", "JIRA_CLOSED_STATUSES",
    "CONFLUENCE_BASE_URL", "CONFLUENCE_SPACE_KEY", "CONFLUENCE_PARENT_ID",
    "SLACK_WEBHOOK_URL",
    "LLM_API_KEY", "LLM_MODEL",
    "ENABLE_CONFLUENCE_PUBLISH", "ENABLE_SLACK_NOTIFY",
    "DRY_RUN", "LOOKBACK_DAYS",
    "GITBOOK_PUBLIC_URL", "GITBOOK_CACHE_PATH", "GITBOOK_REQUEST_DELAY_SECONDS",
]:
```

- [ ] **Step 2: Adicionar teste falhando em `tests/test_settings.py`**

Acrescentar no fim do arquivo:

```python
def test_gitbook_defaults(monkeypatch):
    _set_required(monkeypatch)
    s = Settings(_env_file=None)
    assert s.gitbook_public_url == "https://kobeapps.gitbook.io/kobe.io-documentacao"
    assert str(s.gitbook_cache_path) == "kiro/data/gitbook_public_cache.json"
    assert s.gitbook_request_delay_seconds == 0.5


def test_gitbook_overrides(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("GITBOOK_PUBLIC_URL", "https://example.com/docs")
    monkeypatch.setenv("GITBOOK_CACHE_PATH", "/tmp/cache.json")
    monkeypatch.setenv("GITBOOK_REQUEST_DELAY_SECONDS", "1.5")
    s = Settings(_env_file=None)
    assert s.gitbook_public_url == "https://example.com/docs"
    assert str(s.gitbook_cache_path) == "/tmp/cache.json"
    assert s.gitbook_request_delay_seconds == 1.5
```

- [ ] **Step 3: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_settings.py::test_gitbook_defaults -v`
Expected: FAIL com `AttributeError: 'Settings' object has no attribute 'gitbook_public_url'`.

- [ ] **Step 4: Implementar settings em `kiro/config/settings.py`**

Localizar o bloco `# ─── Pipeline ───────────────────────────────────────────────────` (linha 71) e adicionar antes dele:

```python
    # ─── GitBook RAG (opcional) ─────────────────────────────────────
    gitbook_public_url: str = "https://kobeapps.gitbook.io/kobe.io-documentacao"
    gitbook_cache_path: Path = Path("kiro/data/gitbook_public_cache.json")
    gitbook_request_delay_seconds: float = Field(default=0.5, ge=0.0)
```

- [ ] **Step 5: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_settings.py -v`
Expected: 9 testes passados (7 antigos + 2 novos).

- [ ] **Step 6: Commit**

```bash
git add kiro/config/settings.py tests/conftest.py tests/test_settings.py
git commit -m "feat(config): adicionar GITBOOK_PUBLIC_URL, _CACHE_PATH e _REQUEST_DELAY_SECONDS

Defaults razoáveis pra GitBook pública da Kobe. Todos overridable
via .env. Sem segredos (URL é pública). Refs #2"
```

---

## Task 3: Domain models — `GitBookChunk` e `ScrapingResult` (TDD)

**Files:**
- Modify: `kiro/domain/models.py`
- Create: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Ler `kiro/domain/models.py` pra entender o estilo existente**

Run: `cat kiro/domain/models.py | head -50`
Note: estilo de `@dataclass(frozen=True)` ou Pydantic; manter consistência.

- [ ] **Step 2: Criar `tests/test_gitbook_loader.py` com primeiros 2 testes**

Conteúdo inicial:

```python
"""Testes do scraper de GitBook público (issue #2)."""

import pytest

from kiro.domain.models import GitBookChunk, ScrapingResult


def test_gitbook_chunk_is_frozen():
    chunk = GitBookChunk(
        page_title="Config push",
        page_url="https://example.com/p1",
        section_title="Pré-requisitos",
        section_anchor="pre-requisitos",
        content="Antes de começar...",
    )
    assert chunk.char_count == len("Antes de começar...")
    with pytest.raises(Exception):
        chunk.content = "outro"  # frozen dataclass


def test_scraping_result_holds_summary():
    result = ScrapingResult(
        pages_fetched=10,
        chunks_written=42,
        failed_urls=["https://example.com/dead"],
        output_path="cache.json",
    )
    assert result.pages_fetched == 10
    assert result.chunks_written == 42
    assert result.failed_urls == ["https://example.com/dead"]
    assert result.output_path == "cache.json"
```

- [ ] **Step 3: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: FAIL com `ImportError: cannot import name 'GitBookChunk'`.

- [ ] **Step 4: Implementar dataclasses em `kiro/domain/models.py`**

Adicionar no fim do arquivo (se o arquivo usa dataclasses, seguir o padrão; se usa Pydantic, usar `BaseModel` com `model_config = ConfigDict(frozen=True)`):

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GitBookChunk:
    """Um pedaço de uma página do GitBook, indexado por seção.

    O `char_count` é derivável mas pré-calculado pra evitar recontagem
    no retrieval da issue #3.
    """
    page_title: str
    page_url: str
    section_title: str
    section_anchor: str
    content: str

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class ScrapingResult:
    """Resumo de uma execução do scraper."""
    pages_fetched: int
    chunks_written: int
    failed_urls: list[str]
    output_path: str
```

(Se o arquivo já tiver `from dataclasses import dataclass`, não duplicar o import. Idem `from pathlib import Path`.)

- [ ] **Step 5: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add kiro/domain/models.py tests/test_gitbook_loader.py
git commit -m "feat(domain): GitBookChunk e ScrapingResult dataclasses

Tipos consumidos pelo scraper (issue #2) e pelo retrieval futuro
(issue #3). Vive em domain pra seguir o padrão de Ticket. Refs #2"
```

---

## Task 4: Sitemap parser — XML puro (TDD)

**Files:**
- Create: `kiro/infrastructure/gitbook_loader.py`
- Modify: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Adicionar 3 testes ao final de `tests/test_gitbook_loader.py`**

```python
from kiro.infrastructure.gitbook_loader import _parse_sitemap

SITEMAP_OK = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://kobeapps.gitbook.io/kobe.io-documentacao/intro</loc></url>
  <url><loc>https://kobeapps.gitbook.io/kobe.io-documentacao/setup</loc></url>
  <url><loc>https://kobeapps.gitbook.io/kobe.io-documentacao/intro</loc></url>
</urlset>
"""

SITEMAP_WITH_EXTERNAL = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://kobeapps.gitbook.io/kobe.io-documentacao/intro</loc></url>
  <url><loc>https://outro-site.com/some-page</loc></url>
</urlset>
"""


def test_sitemap_parsing_dedupes():
    urls = _parse_sitemap(SITEMAP_OK, base_url="https://kobeapps.gitbook.io/kobe.io-documentacao")
    assert len(urls) == 2
    assert "https://kobeapps.gitbook.io/kobe.io-documentacao/intro" in urls
    assert "https://kobeapps.gitbook.io/kobe.io-documentacao/setup" in urls


def test_sitemap_filters_external_urls():
    urls = _parse_sitemap(SITEMAP_WITH_EXTERNAL, base_url="https://kobeapps.gitbook.io/kobe.io-documentacao")
    assert urls == ["https://kobeapps.gitbook.io/kobe.io-documentacao/intro"]


def test_sitemap_invalid_xml_raises():
    with pytest.raises(ValueError, match="sitemap"):
        _parse_sitemap("not xml at all", base_url="https://kobeapps.gitbook.io/kobe.io-documentacao")
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py::test_sitemap_parsing_dedupes -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'kiro.infrastructure.gitbook_loader'`.

- [ ] **Step 3: Criar `kiro/infrastructure/gitbook_loader.py` com header e parser**

```python
"""Scraper do GitBook público da Kobe.

Baixa todas as páginas listadas no `/sitemap.xml` do GitBook, quebra cada
uma em chunks por heading, e salva como JSON pra ser consumido pelo
retrieval (issue #3). Esse módulo NÃO toca o pipeline de geração.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

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
        if not url.startswith(base_normalized):
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
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add kiro/infrastructure/gitbook_loader.py tests/test_gitbook_loader.py
git commit -m "feat(gitbook): parser de sitemap.xml com filtro por base_url

- _parse_sitemap(content, base_url) → list[str] deduplicada
- Filtra URLs fora de base_url (defesa contra sitemap apontar pra fora)
- Levanta ValueError em XML inválido ou sem URLs casando

Pure function, sem IO — IO vem na próxima task. Refs #2"
```

---

## Task 5: HTML helpers — container, page_title, slug (TDD)

**Files:**
- Modify: `kiro/infrastructure/gitbook_loader.py`
- Modify: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Adicionar testes em `tests/test_gitbook_loader.py`**

No topo do arquivo, adicionar:
```python
from bs4 import BeautifulSoup
from kiro.infrastructure.gitbook_loader import (
    _extract_page_title,
    _find_content_container,
    _section_anchor,
)
```

E no fim:
```python
def test_find_container_prefers_main():
    soup = BeautifulSoup(
        '<html><body><main><h1>X</h1></main></body></html>',
        "html.parser",
    )
    container = _find_content_container(soup)
    assert container.name == "main"


def test_find_container_falls_back_to_testid():
    soup = BeautifulSoup(
        '<html><body><div data-testid="page.contentEditor"><h1>X</h1></div></body></html>',
        "html.parser",
    )
    container = _find_content_container(soup)
    assert container.get("data-testid") == "page.contentEditor"


def test_find_container_falls_back_to_article():
    soup = BeautifulSoup(
        '<html><body><article><h1>X</h1></article></body></html>',
        "html.parser",
    )
    container = _find_content_container(soup)
    assert container.name == "article"


def test_find_container_returns_none_when_nothing_matches():
    soup = BeautifulSoup("<html><body><p>x</p></body></html>", "html.parser")
    assert _find_content_container(soup) is None


def test_page_title_from_h1():
    soup = BeautifulSoup(
        '<html><head><title>Site</title></head><body><main><h1>Tópico</h1></main></body></html>',
        "html.parser",
    )
    assert _extract_page_title(soup) == "Tópico"


def test_page_title_falls_back_to_title_tag():
    soup = BeautifulSoup(
        '<html><head><title>Fallback title</title></head><body><main><p>sem h1</p></main></body></html>',
        "html.parser",
    )
    assert _extract_page_title(soup) == "Fallback title"


def test_section_anchor_from_heading_id():
    soup = BeautifulSoup('<h2 id="pre-requisitos">Pré-requisitos</h2>', "html.parser")
    heading = soup.find("h2")
    assert _section_anchor(heading) == "pre-requisitos"


def test_section_anchor_slugifies_text():
    soup = BeautifulSoup("<h2>Configurando Notificações Push!</h2>", "html.parser")
    heading = soup.find("h2")
    assert _section_anchor(heading) == "configurando-notificacoes-push"
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: vários FAIL com `ImportError: cannot import name '_find_content_container'`.

- [ ] **Step 3: Implementar helpers em `kiro/infrastructure/gitbook_loader.py`**

Adicionar no topo do arquivo (após o existente):
```python
import re
import unicodedata
from typing import Optional

from bs4 import BeautifulSoup, Tag
```

E adicionar as funções no fim do arquivo:

```python
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
    """Título da página: primeiro <h1> do conteúdo, ou <title> como fallback."""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    title = soup.find("title")
    if title and title.get_text(strip=True):
        return title.get_text(strip=True)
    return "(sem título)"


def _section_anchor(heading: Tag) -> str:
    """Anchor pra deep-link. Usa heading.id se presente, senão slugifica texto."""
    if heading.get("id"):
        return heading["id"]
    return _slugify(heading.get_text(strip=True))


def _slugify(text: str) -> str:
    """Slug ASCII simples: minúsculas, remove acentos, troca não-alfanum por '-'."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    lowered = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add kiro/infrastructure/gitbook_loader.py tests/test_gitbook_loader.py
git commit -m "feat(gitbook): helpers de HTML — container, page_title, slug

- _find_content_container: <main> → testid → <article>
- _extract_page_title: <h1> → <title>
- _section_anchor: heading.id → slugify do texto
- _slugify: ASCII-safe, sem deps externas

Tudo pure functions sobre BeautifulSoup. Refs #2"
```

---

## Task 6: Chunker por heading (TDD)

**Files:**
- Modify: `kiro/infrastructure/gitbook_loader.py`
- Modify: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Adicionar testes ao fim de `tests/test_gitbook_loader.py`**

```python
from kiro.infrastructure.gitbook_loader import _chunk_page


def test_chunk_by_heading_three_sections():
    html = """
    <main>
      <h1>Página</h1>
      <h2>Introdução</h2>
      <p>Texto da introdução suficiente pra teste.</p>
      <h2>Configuração</h2>
      <p>Passo um.</p>
      <p>Passo dois.</p>
      <h2>Conclusão</h2>
      <p>Fim.</p>
    </main>
    """
    chunks = _chunk_page(html, page_url="https://x.com/p1")
    assert [c.section_title for c in chunks] == ["Introdução", "Configuração", "Conclusão"]
    assert all(c.page_title == "Página" for c in chunks)
    assert all(c.page_url == "https://x.com/p1" for c in chunks)
    assert "Passo um" in chunks[1].content
    assert "Passo dois" in chunks[1].content


def test_chunk_keeps_short_section():
    html = """
    <main>
      <h1>Página</h1>
      <h2>Limite iOS</h2>
      <p>Suporte apenas iOS 15+.</p>
    </main>
    """
    chunks = _chunk_page(html, page_url="https://x.com/p1")
    assert len(chunks) == 1
    assert chunks[0].section_title == "Limite iOS"
    assert "iOS 15+" in chunks[0].content
    assert chunks[0].char_count < 50


def test_chunk_returns_empty_when_no_container():
    chunks = _chunk_page("<html><body><p>nada</p></body></html>", page_url="https://x.com/p1")
    assert chunks == []


def test_chunk_uses_intro_section_when_text_before_first_heading():
    html = """
    <main>
      <h1>Página</h1>
      <p>Intro sem heading próprio.</p>
      <h2>Seção</h2>
      <p>Conteúdo.</p>
    </main>
    """
    chunks = _chunk_page(html, page_url="https://x.com/p1")
    assert len(chunks) == 2
    assert chunks[0].section_title == "Página"
    assert "Intro sem heading próprio" in chunks[0].content
    assert chunks[1].section_title == "Seção"
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py::test_chunk_by_heading_three_sections -v`
Expected: FAIL com `ImportError: cannot import name '_chunk_page'`.

- [ ] **Step 3: Implementar `_chunk_page` em `kiro/infrastructure/gitbook_loader.py`**

Adicionar import no topo (já tem BeautifulSoup):
```python
from kiro.domain.models import GitBookChunk
```

E adicionar as funções no fim do arquivo:

```python
_HEADING_TAGS = {"h1", "h2", "h3"}


def _chunk_page(html: str, page_url: str) -> list[GitBookChunk]:
    """Quebra a página em chunks por heading (h1/h2/h3).

    Texto antes do primeiro heading é atribuído a uma "seção intro"
    com title = page_title. Seções > 1000 chars são sub-divididas.
    Seções < 200 chars são preservadas (info curta também é útil).

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
        # Pula descendants dentro de heading (já capturado pelo heading)
        if element.find_parent(_HEADING_TAGS - {element.name} if element.name in _HEADING_TAGS else _HEADING_TAGS):
            # Defensivo: evita pegar <span> dentro de <h2> como parágrafo
            if element.name not in _HEADING_TAGS:
                continue
        if element.name in _HEADING_TAGS:
            # Fecha a seção atual antes de abrir a nova
            if current_paragraphs:
                sections.append((current_title, current_anchor, current_paragraphs))
            current_title = element.get_text(strip=True) or "(sem título)"
            current_anchor = _section_anchor(element)
            current_paragraphs = []
        elif element.name in {"p", "li"}:
            text = element.get_text(separator=" ", strip=True)
            if text:
                current_paragraphs.append(text)

    # Fecha última seção
    if current_paragraphs:
        sections.append((current_title, current_anchor, current_paragraphs))

    # Materializa chunks (sub-dividir quando >1000 chars vem na Task 7)
    chunks: list[GitBookChunk] = []
    for title, anchor, paragraphs in sections:
        content = "\n\n".join(paragraphs).strip()
        if not content:
            continue
        chunks.append(
            GitBookChunk(
                page_title=page_title,
                page_url=page_url,
                section_title=title,
                section_anchor=anchor,
                content=content,
            )
        )
    return chunks
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add kiro/infrastructure/gitbook_loader.py tests/test_gitbook_loader.py
git commit -m "feat(gitbook): chunking por heading (h1/h2/h3)

- Itera descendants do container, quebra a cada heading
- Texto antes do 1º heading vira seção 'intro' com title=page_title
- Captura <p> e <li>; ignora descendants dentro de heading
- Sem sub-divisão por tamanho ainda — vem na próxima task

Refs #2"
```

---

## Task 7: Sub-divisão de seções grandes (TDD)

**Files:**
- Modify: `kiro/infrastructure/gitbook_loader.py`
- Modify: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Adicionar testes ao fim de `tests/test_gitbook_loader.py`**

```python
def test_chunk_split_when_oversized():
    # 5 parágrafos de ~500 chars cada → ~2500 chars total
    big_paragraph = "Parágrafo bem longo. " * 30  # ~600 chars
    paragraphs_html = "".join(f"<p>{big_paragraph}</p>" for _ in range(5))
    html = f"<main><h1>Página</h1><h2>Grande</h2>{paragraphs_html}</main>"

    chunks = _chunk_page(html, page_url="https://x.com/big")

    # Deve gerar múltiplos sub-chunks, todos com mesmo section_title
    assert len(chunks) >= 2
    assert all(c.section_title == "Grande" for c in chunks)
    assert all(c.section_anchor == "grande" for c in chunks)
    # Cada sub-chunk deve respeitar ~1000 chars
    assert all(c.char_count <= 1100 for c in chunks)
    # Soma dos sub-chunks ≈ conteúdo total (sem perder texto)
    total_text = "\n\n".join(c.content for c in chunks)
    assert "Parágrafo bem longo." in total_text


def test_chunk_split_at_paragraph_boundary():
    # 3 parágrafos médios — deve quebrar entre parágrafos, não no meio de um
    para = "A" * 400  # 400 chars cada
    html = f"<main><h1>P</h1><h2>S</h2><p>{para}</p><p>{para}</p><p>{para}</p></main>"

    chunks = _chunk_page(html, page_url="https://x.com/m")

    # Cada chunk termina onde um parágrafo termina (sem 'A' órfão)
    for chunk in chunks:
        # Conteúdo não pode terminar com parte de um 'AAA...' truncado:
        # cada chunk deve consistir só de parágrafos completos
        parts = chunk.content.split("\n\n")
        for part in parts:
            assert part.strip() in (para, "")
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py::test_chunk_split_when_oversized -v`
Expected: FAIL — só 1 chunk grande gerado.

- [ ] **Step 3: Adicionar `_split_oversized` e ligar ao chunker**

Em `kiro/infrastructure/gitbook_loader.py`, adicionar antes do `_chunk_page`:

```python
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
```

E modificar o trecho final de `_chunk_page` (o loop que materializa chunks) pra usar `_split_oversized`:

```python
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
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add kiro/infrastructure/gitbook_loader.py tests/test_gitbook_loader.py
git commit -m "feat(gitbook): sub-divide seções > 1000 chars em sub-chunks

- _split_oversized: quebra em fim de parágrafo, target 800 chars
- Sub-chunks preservam section_title e section_anchor
- Parágrafo gigante isolado fica como sub-chunk único (não quebra no meio)

Refs #2"
```

---

## Task 8: Persistência JSON com fetched_at (TDD)

**Files:**
- Modify: `kiro/infrastructure/gitbook_loader.py`
- Modify: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Adicionar testes ao fim de `tests/test_gitbook_loader.py`**

```python
import json
from kiro.infrastructure.gitbook_loader import _write_cache


def test_write_cache_creates_file_with_correct_schema(tmp_path):
    chunks = [
        GitBookChunk(
            page_title="P1",
            page_url="https://x.com/p1",
            section_title="S1",
            section_anchor="s1",
            content="Conteúdo 1",
        ),
    ]
    out = tmp_path / "cache.json"
    _write_cache(
        chunks,
        output_path=out,
        base_url="https://x.com",
    )

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["source"] == "gitbook_public"
    assert data["base_url"] == "https://x.com"
    assert isinstance(data["fetched_at"], str)
    assert len(data["chunks"]) == 1
    chunk = data["chunks"][0]
    assert chunk["page_title"] == "P1"
    assert chunk["page_url"] == "https://x.com/p1"
    assert chunk["section_title"] == "S1"
    assert chunk["section_anchor"] == "s1"
    assert chunk["content"] == "Conteúdo 1"
    assert chunk["char_count"] == len("Conteúdo 1")


def test_fetched_at_is_iso8601_utc(tmp_path):
    out = tmp_path / "cache.json"
    _write_cache([], output_path=out, base_url="https://x.com")
    data = json.loads(out.read_text(encoding="utf-8"))
    # Formato ISO 8601 UTC: termina em 'Z' ou '+00:00'
    fetched = data["fetched_at"]
    assert fetched.endswith("Z") or fetched.endswith("+00:00")
    # Parseável de volta como datetime
    from datetime import datetime
    parsed = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_write_cache_creates_parent_dirs(tmp_path):
    out = tmp_path / "nested" / "dir" / "cache.json"
    _write_cache([], output_path=out, base_url="https://x.com")
    assert out.exists()
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py::test_write_cache_creates_file_with_correct_schema -v`
Expected: FAIL com `ImportError: cannot import name '_write_cache'`.

- [ ] **Step 3: Implementar em `kiro/infrastructure/gitbook_loader.py`**

Adicionar imports no topo:
```python
import json
from datetime import datetime, timezone
```

E adicionar a função no fim:

```python
def _write_cache(
    chunks: list[GitBookChunk],
    output_path: Path,
    base_url: str,
) -> None:
    """Grava o cache JSON. `fetched_at` no topo (não por chunk)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "gitbook_public",
        "base_url": base_url,
        "chunks": [
            {
                "page_title": c.page_title,
                "page_url": c.page_url,
                "section_title": c.section_title,
                "section_anchor": c.section_anchor,
                "content": c.content,
                "char_count": c.char_count,
            }
            for c in chunks
        ],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add kiro/infrastructure/gitbook_loader.py tests/test_gitbook_loader.py
git commit -m "feat(gitbook): persistência JSON com fetched_at no topo

- Schema: {fetched_at, source, base_url, chunks: [...]}
- fetched_at em ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ')
- Cria diretórios pais automaticamente
- ensure_ascii=False pra preservar PT-BR; indent=2 pra debugar

Refs #2"
```

---

## Task 9: Orchestrator + fetch HTTP (TDD com respx)

**Files:**
- Modify: `kiro/infrastructure/gitbook_loader.py`
- Modify: `tests/test_gitbook_loader.py`

- [ ] **Step 1: Adicionar testes ao fim de `tests/test_gitbook_loader.py`**

```python
import httpx
import respx
from kiro.infrastructure.gitbook_loader import scrape_public_gitbook

_PAGE_HTML = """<html><head><title>X</title></head><body>
<main>
  <h1>Configurando push</h1>
  <h2>Pré-requisitos</h2>
  <p>Antes de começar, certifique-se de que sua conta Firebase está ativa.</p>
  <h2>Passos</h2>
  <p>Passo 1: abra o console.</p>
  <p>Passo 2: clique em Notifications.</p>
</main>
</body></html>"""

_PAGE_404_BODY = "<html><body>404</body></html>"


@respx.mock
def test_sitemap_404_raises(tmp_path):
    base = "https://example.com/docs"
    respx.get(f"{base}/sitemap.xml").mock(return_value=httpx.Response(404))

    with pytest.raises(ValueError, match="sitemap"):
        scrape_public_gitbook(
            base_url=base,
            output_path=tmp_path / "cache.json",
            request_delay_seconds=0,
        )


@respx.mock
def test_page_404_continues(tmp_path):
    base = "https://example.com/docs"
    sitemap = f"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/ok</loc></url>
  <url><loc>{base}/dead</loc></url>
</urlset>"""
    respx.get(f"{base}/sitemap.xml").mock(return_value=httpx.Response(200, text=sitemap))
    respx.get(f"{base}/ok").mock(return_value=httpx.Response(200, text=_PAGE_HTML))
    respx.get(f"{base}/dead").mock(return_value=httpx.Response(404, text=_PAGE_404_BODY))

    result = scrape_public_gitbook(
        base_url=base,
        output_path=tmp_path / "cache.json",
        request_delay_seconds=0,
    )

    assert result.pages_fetched == 1
    assert result.chunks_written >= 1
    assert f"{base}/dead" in result.failed_urls


@respx.mock
def test_full_pipeline_with_mocks(tmp_path):
    base = "https://example.com/docs"
    sitemap = f"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/intro</loc></url>
  <url><loc>{base}/setup</loc></url>
</urlset>"""
    respx.get(f"{base}/sitemap.xml").mock(return_value=httpx.Response(200, text=sitemap))
    respx.get(f"{base}/intro").mock(return_value=httpx.Response(200, text=_PAGE_HTML))
    respx.get(f"{base}/setup").mock(return_value=httpx.Response(200, text=_PAGE_HTML))

    out = tmp_path / "cache.json"
    result = scrape_public_gitbook(
        base_url=base,
        output_path=out,
        request_delay_seconds=0,
    )

    assert result.pages_fetched == 2
    assert result.failed_urls == []
    assert result.output_path == str(out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["source"] == "gitbook_public"
    assert data["base_url"] == base
    assert len(data["chunks"]) >= 2
    assert data["chunks"][0]["page_title"] == "Configurando push"
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py::test_full_pipeline_with_mocks -v`
Expected: FAIL com `ImportError: cannot import name 'scrape_public_gitbook'`.

- [ ] **Step 3: Implementar fetch + orchestrator em `kiro/infrastructure/gitbook_loader.py`**

Adicionar imports no topo:
```python
import time
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kiro.domain.models import GitBookChunk, ScrapingResult
from kiro.utils.progress import Narrator
```

(Se `GitBookChunk` já estava importado, não duplicar.)

Adicionar funções de fetch e orchestrator no fim do arquivo:

```python
@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _fetch_url(client: httpx.Client, url: str) -> str:
    """GET com retry em 408/429/5xx e timeouts de rede. Retorna text."""
    resp = client.get(url)
    if resp.status_code in (408, 429) or resp.status_code >= 500:
        resp.raise_for_status()  # dispara retry
    if resp.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}", request=resp.request, response=resp
        )
    return resp.text


def scrape_public_gitbook(
    base_url: str,
    output_path: Path,
    *,
    narrator: Optional[Narrator] = None,
    request_delay_seconds: float = 0.5,
    timeout_seconds: float = 30.0,
) -> ScrapingResult:
    """Baixa a GitBook pública e grava cache JSON.

    Args:
        base_url: URL raiz da GitBook (ex.: https://kobeapps.gitbook.io/docs).
        output_path: Caminho do JSON de saída.
        narrator: Narrator pra spinner; None desabilita.
        request_delay_seconds: Pausa entre requisições (educação com servidor).
        timeout_seconds: Timeout por requisição.

    Returns:
        ScrapingResult com contagens e lista de URLs que falharam.

    Raises:
        ValueError: sitemap.xml inacessível, inválido ou sem URLs.
    """
    output_path = Path(output_path)
    base_url = base_url.rstrip("/")

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        # 1. Sitemap
        sitemap_url = f"{base_url}/sitemap.xml"
        try:
            sitemap_content = _fetch_url(client, sitemap_url)
        except httpx.HTTPError as e:
            raise ValueError(
                f"sitemap inacessível em {sitemap_url}: {e}. "
                "Verifique GITBOOK_PUBLIC_URL."
            ) from e

        urls = _parse_sitemap(sitemap_content, base_url=base_url)
        log.info("gitbook: %d páginas no sitemap", len(urls))
        if narrator is not None:
            narrator.done(f"{len(urls)} páginas encontradas no sitemap")

        # 2. Fetch cada página → chunks
        all_chunks: list[GitBookChunk] = []
        failed: list[str] = []

        for index, url in enumerate(urls, start=1):
            try:
                if narrator is not None:
                    with narrator.step(f"baixando {index}/{len(urls)}: {url}"):
                        html = _fetch_url(client, url)
                else:
                    html = _fetch_url(client, url)
                page_chunks = _chunk_page(html, page_url=url)
                if not page_chunks:
                    log.warning("gitbook: 0 chunks gerados pra %s", url)
                    failed.append(url)
                else:
                    all_chunks.extend(page_chunks)
            except httpx.HTTPError as e:
                log.warning("gitbook: falha em %s: %s", url, e)
                failed.append(url)
            except Exception as e:
                log.warning("gitbook: erro parseando %s: %s", url, e)
                failed.append(url)

            if request_delay_seconds > 0 and index < len(urls):
                time.sleep(request_delay_seconds)

    # 3. Persistir
    _write_cache(all_chunks, output_path=output_path, base_url=base_url)

    return ScrapingResult(
        pages_fetched=len(urls) - len(failed),
        chunks_written=len(all_chunks),
        failed_urls=failed,
        output_path=str(output_path),
    )
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_gitbook_loader.py -v`
Expected: 25 passed.

- [ ] **Step 5: Rodar a suíte completa pra garantir que nada quebrou**

Run: `.venv/bin/python -m pytest -q`
Expected: ~84 passed (57 antigos + 9 do test_settings/test_gitbook_loader + 25 novos = ajustar conta — pelo menos > 80).

- [ ] **Step 6: Commit**

```bash
git add kiro/infrastructure/gitbook_loader.py tests/test_gitbook_loader.py
git commit -m "feat(gitbook): scrape_public_gitbook — orchestrator end-to-end

- Lê /sitemap.xml (raise se inacessível)
- Itera URLs, faz fetch com tenacity (retry 408/429/5xx)
- Página individual falhando vai pra failed_urls; pipeline continua
- Throttle configurável entre requisições
- Persiste cache + retorna ScrapingResult com sumário

Cobertura: 8 testes inclui pipeline end-to-end com respx. Refs #2"
```

---

## Task 10: CLI subcomando `fetch-gitbook --public` (TDD)

**Files:**
- Modify: `kiro/interfaces/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Criar `tests/test_cli.py` com teste de dispatch**

```python
"""Smoke tests do CLI — confirma que subcomandos são roteados."""

from unittest.mock import patch

import pytest

from kiro.interfaces.cli import build_parser, main


def test_parser_aceita_fetch_gitbook_public(monkeypatch):
    parser = build_parser()
    args = parser.parse_args(["fetch-gitbook", "--public"])
    assert args.command == "fetch-gitbook"
    assert args.public is True


def test_parser_exige_public_flag(monkeypatch):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["fetch-gitbook"])  # sem --public, --internal etc


def _set_required(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USER_EMAIL", "u@x.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-xyz")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
    monkeypatch.setenv("LLM_API_KEY", "sk-abc")


def test_main_dispatches_to_scraper(monkeypatch, tmp_path):
    _set_required(monkeypatch)
    monkeypatch.setenv("GITBOOK_CACHE_PATH", str(tmp_path / "cache.json"))

    with patch(
        "kiro.interfaces.cli.scrape_public_gitbook"
    ) as mock_scrape:
        from kiro.domain.models import ScrapingResult
        mock_scrape.return_value = ScrapingResult(
            pages_fetched=3,
            chunks_written=10,
            failed_urls=[],
            output_path=str(tmp_path / "cache.json"),
        )

        rc = main(["fetch-gitbook", "--public"])

    assert rc == 0
    assert mock_scrape.called
    kwargs = mock_scrape.call_args.kwargs
    args_pos = mock_scrape.call_args.args
    # Aceita chamada com kwargs OU args:
    base_url = kwargs.get("base_url") or args_pos[0]
    output_path = kwargs.get("output_path") or args_pos[1]
    assert "kobeapps.gitbook.io" in base_url
    assert "cache.json" in str(output_path)
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL — `argparse: invalid choice: 'fetch-gitbook'`.

- [ ] **Step 3: Atualizar `kiro/interfaces/cli.py`**

Adicionar import no topo (após os existentes):
```python
from kiro.infrastructure.gitbook_loader import scrape_public_gitbook
```

Em `build_parser()`, após `sub.add_parser("config-check", ...)` e antes de `return parser`:

```python
    fetch_p = sub.add_parser(
        "fetch-gitbook",
        help="Baixa o GitBook e gera cache JSON (RAG).",
    )
    source_group = fetch_p.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--public",
        action="store_true",
        help="Baixa a GitBook pública (sem auth).",
    )
    fetch_p.add_argument(
        "--verbose",
        action="store_true",
        help="Mostra logs detalhados em vez do spinner.",
    )
```

Em `main()`, após o branch `if args.command == "config-check":`, adicionar:

```python
    if args.command == "fetch-gitbook":
        verbose = getattr(args, "verbose", False)
        narrator = Narrator(enabled=not verbose)
        if not verbose:
            logging.getLogger("kiro").setLevel(logging.ERROR)

        print_banner()
        narrator.section("GitBook · fetch público")

        try:
            result = scrape_public_gitbook(
                base_url=settings.gitbook_public_url,
                output_path=settings.gitbook_cache_path,
                narrator=narrator,
                request_delay_seconds=settings.gitbook_request_delay_seconds,
            )
        except ValueError as e:
            narrator.fail(str(e))
            return 1

        narrator.done(
            f"{result.pages_fetched} páginas baixadas, "
            f"{len(result.failed_urls)} falhas"
        )
        narrator.done(
            f"{result.chunks_written} chunks salvos em {result.output_path}"
        )
        if verbose and result.failed_urls:
            narrator.warn("URLs que falharam:")
            for url in result.failed_urls:
                narrator.info(f"  {url}")
        return 0 if result.chunks_written > 0 else 1
```

- [ ] **Step 4: Rodar pra ver passar**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv/bin/python -m pytest -q`
Expected: tudo verde, ~28 testes novos no total (2 settings + 25 gitbook_loader + 3 cli).

- [ ] **Step 6: Commit**

```bash
git add kiro/interfaces/cli.py tests/test_cli.py
git commit -m "feat(cli): subcomando 'kiro fetch-gitbook --public'

- --public é mutuamente exclusivo (futuro --internal vem na issue #4)
- Usa Narrator pra spinner durante download
- Verbose lista URLs que falharam
- Retorna rc=1 se nenhum chunk foi gerado

Refs #2 closes #2"
```

---

## Task 11: Verificação manual contra GitBook real + ajustes finais

**Files:** nenhum esperado (apenas execução real e eventuais correções).

- [ ] **Step 1: Rodar o comando contra o GitBook real**

Run: `.venv/bin/python -m kiro.interfaces.cli fetch-gitbook --public --verbose`
Expected:
- Banner KIRO aparece
- Spinner mostra "baixando X/N"
- Termina com "✓ N páginas baixadas, M falhas"
- Cria `kiro/data/gitbook_public_cache.json`

- [ ] **Step 2: Validar o cache gerado**

Run:
```bash
jq '. | {fetched_at, source, base_url, chunk_count: (.chunks | length)}' kiro/data/gitbook_public_cache.json
```

Expected:
- `fetched_at` é um timestamp ISO recente
- `source` = `"gitbook_public"`
- `chunk_count` entre 50 e 300

- [ ] **Step 3: Inspecionar 3 chunks pra qualidade**

Run:
```bash
jq '.chunks[0:3] | .[] | {page_title, section_title, char_count, sample: (.content[0:100])}' kiro/data/gitbook_public_cache.json
```

Expected: titles e contents em PT-BR coerente, sem HTML cru, sem JS, sem listas de navegação contaminando.

- [ ] **Step 4: Confirmar que o cache NÃO foi staged pelo git**

Run: `git status`
Expected: working tree clean (cache ignorado pelo `.gitignore`).

- [ ] **Step 5: Se a estrutura do container não bateu (zero chunks ou lixo)**

Diagnóstico:
```bash
.venv/bin/python -c "
import httpx
from bs4 import BeautifulSoup
r = httpx.get('https://kobeapps.gitbook.io/kobe.io-documentacao/', timeout=30, follow_redirects=True)
soup = BeautifulSoup(r.text, 'html.parser')
print('main:', bool(soup.find('main')))
print('testid:', bool(soup.find(attrs={'data-testid': 'page.contentEditor'})))
print('article:', bool(soup.find('article')))
print('h1:', soup.find('h1').get_text() if soup.find('h1') else None)
"
```

Ajustar `_find_content_container` em `kiro/infrastructure/gitbook_loader.py` pra incluir o seletor real do GitBook atual, e adicionar um teste cobrindo o novo fallback (TDD: test → fail → fix → pass). Commit como `fix(gitbook): novo seletor de container pra render atual da GitBook`.

- [ ] **Step 6: Push da branch e abrir PR**

```bash
git push -u origin feature/gitbook-scraper
gh pr create --title "feat(rag): GitBook public scraper + cache JSON" --body "$(cat <<'EOF'
Closes #2

## Resumo

Primeiro tijolo do RAG da V1.1. Esse PR baixa a GitBook pública da Kobe e
gera um cache JSON com chunks por seção, sem tocar no pipeline de geração.
A integração com retrieval vem na issue #3.

## Mudanças

### Config
- 3 settings novos: `GITBOOK_PUBLIC_URL`, `GITBOOK_CACHE_PATH`, `GITBOOK_REQUEST_DELAY_SECONDS`
- `.env.example` atualizado
- `.gitignore` ignora `kiro/data/*_cache.json`

### Domain
- `GitBookChunk` e `ScrapingResult` dataclasses em `kiro/domain/models.py`

### Infrastructure
- Novo `kiro/infrastructure/gitbook_loader.py`:
  - `_parse_sitemap` (XML puro, dedup, filtro por base_url)
  - Helpers HTML: `_find_content_container`, `_extract_page_title`, `_section_anchor`
  - `_chunk_page` quebra por h1/h2/h3, sub-divide seções > 1000 chars
  - `_write_cache` grava JSON com `fetched_at` ISO 8601 UTC
  - `scrape_public_gitbook` orchestrator com httpx + tenacity

### CLI
- Subcomando `kiro fetch-gitbook --public`
- Usa Narrator pra spinner; `--verbose` mostra falhas

### Testes
- 28 testes novos (2 settings + 25 gitbook_loader + 3 CLI), todos isolados de rede via respx

## Verificação local

\`\`\`bash
.venv/bin/python -m pytest -q   # tudo verde
kiro fetch-gitbook --public --verbose
jq '.chunks | length' kiro/data/gitbook_public_cache.json  # 50-300
\`\`\`

## Fora de escopo

- Retrieval / busca → issue #3
- GitBook interno autenticado → issue #4
- Confluence SUP scraper → criar issue #6
- Atualização do KIRO.md → issue #5

## Próximos passos

Após merge, abrir branch \`feature/gitbook-retrieval\` pra issue #3.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR aberto, URL retornado.

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task que cobre |
|--------------|----------------|
| Arquitetura (single infra module) | Task 4-9 |
| Contrato público `scrape_public_gitbook` | Task 9 |
| Fluxo de dados | Tasks 4 (sitemap) + 5-7 (parse/chunk) + 8 (persist) + 9 (orchestrator) |
| Schema do cache JSON | Task 8 |
| Discovery via sitemap | Task 4 (parse) + Task 9 (fetch) |
| Parser e chunking por seção | Tasks 5, 6, 7 |
| Error handling (sitemap raise, página continue) | Task 9 |
| CLI | Task 10 |
| Settings | Task 2 |
| `.gitignore` + `.env.example` | Task 1 |
| Estratégia de testes (9 testes) | Coberto: 3 sitemap (T4) + 4 chunking (T6, T7) + short section (T6) + page 404 (T9) + full pipeline (T9) + fetched_at (T8) = 11 testes diretos da estratégia + extras de helpers e CLI |
| Critérios de aceite | Task 11 (verificação manual + jq check) |

Sem lacunas.

**2. Placeholder scan:** Nenhum "TBD"/"TODO" no plano. Todo step com código tem código. Todo comando tem expected output.

**3. Type consistency:** `GitBookChunk` definido em T3 com fields `(page_title, page_url, section_title, section_anchor, content)` + property `char_count`. Usado em T6, T7, T8, T9 com mesmos fields. `ScrapingResult` definido em T3 com `(pages_fetched, chunks_written, failed_urls, output_path)` — usado em T9 e T10 com mesmos fields. `_parse_sitemap(content, base_url)`, `_find_content_container(soup)`, `_chunk_page(html, page_url)`, `_write_cache(chunks, output_path, base_url)`, `scrape_public_gitbook(base_url, output_path, *, narrator, request_delay_seconds, timeout_seconds)` — todas as assinaturas consistentes entre task de definição e tasks que invocam.

Plano pronto.
