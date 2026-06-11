"""Testes do scraper de GitBook público (issue #2)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from kiro.domain.models import GitBookChunk, ScrapingResult
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


def test_gitbook_chunk_is_frozen():
    chunk = GitBookChunk(
        page_title="Config push",
        page_url="https://example.com/p1",
        section_title="Pré-requisitos",
        section_anchor="pre-requisitos",
        content="Antes de começar...",
    )
    assert chunk.char_count == len("Antes de começar...")
    with pytest.raises(ValidationError):
        chunk.content = "outro"  # frozen model


def test_scraping_result_holds_summary():
    result = ScrapingResult(
        pages_fetched=10,
        chunks_written=42,
        failed_urls=["https://example.com/dead"],
        output_path=Path("cache.json"),
    )
    assert result.pages_fetched == 10
    assert result.chunks_written == 42
    assert result.failed_urls == ["https://example.com/dead"]
    assert result.output_path == Path("cache.json")


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
