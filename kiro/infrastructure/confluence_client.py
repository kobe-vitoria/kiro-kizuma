"""Cliente HTTP para Confluence Cloud. Storage Format com escaping."""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kiro.domain.exceptions import ConfluenceError
from kiro.domain.models import ArticleDraft, Cluster
from kiro.utils.branding import CONFLUENCE_FOOTER

_LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[.\)\-]\s+")

log = logging.getLogger(__name__)


class ConfluenceClient:
    def __init__(
        self,
        base_url: str,
        space_key: str,
        user_email: str,
        api_token: str,
        parent_id: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._space_key = space_key
        self._parent_id = parent_id or None
        self._auth = (user_email, api_token)
        self._timeout = timeout_seconds

    def create_draft(self, article: ArticleDraft, cluster: Cluster) -> str:
        month_tag = datetime.now(timezone.utc).strftime("%Y-%m")
        body = self._render_storage(article, cluster)
        payload: dict = {
            "type": "page",
            "status": "draft",
            "title": f"[{month_tag}] {article.title}",
            "space": {"key": self._space_key},
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        if self._parent_id:
            payload["ancestors"] = [{"id": self._parent_id}]
        return self._post(payload)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    def _post(self, payload: dict) -> str:
        try:
            with httpx.Client(auth=self._auth, timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/rest/api/content", json=payload)
                resp.raise_for_status()
                data = resp.json()
                page_id = data["id"]
                url = f"{self._base_url}/pages/{page_id}"
                log.info("confluence: draft criado id=%s", page_id)
                return url
        except httpx.HTTPStatusError as e:
            log.error("confluence HTTP %s", e.response.status_code)
            raise ConfluenceError(
                f"Confluence rejeitou publicação: {e.response.status_code}"
            ) from e
        except (KeyError, ValueError) as e:
            raise ConfluenceError(f"resposta Confluence inesperada: {e}") from e

    @staticmethod
    def _escape(text: str) -> str:
        return (
            (text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @classmethod
    def _render_storage(cls, article: ArticleDraft, cluster: Cluster) -> str:
        esc = cls._escape
        faq_rows = "".join(
            f"<tr><td><strong>{esc(item.question)}</strong></td>"
            f"<td>{esc(item.answer)}</td></tr>"
            for item in article.faq
        )
        faq_block = (
            "<h2>Perguntas Frequentes</h2>"
            "<table><tbody>"
            "<tr><th>Pergunta</th><th>Resposta</th></tr>"
            f"{faq_rows}"
            "</tbody></table>"
        ) if faq_rows else ""

        steps = "".join(
            f"<li>{esc(stripped)}</li>"
            for step in article.solution.split("\n")
            if (stripped := _LEADING_NUMBER_RE.sub("", step).strip())
        )

        tickets_html = " ".join(f"<code>{esc(k)}</code>" for k in cluster.tickets[:10])
        month = datetime.now(timezone.utc).strftime("%Y-%m")

        return (
            '<ac:structured-macro ac:name="info">'
            '<ac:parameter ac:name="title">Rascunho automático</ac:parameter>'
            "<ac:rich-text-body>"
            f"<p>Gerado a partir de <strong>{cluster.count} tickets</strong> em {month}. "
            "Revise antes de publicar.</p>"
            f"<p>Tickets de origem: {tickets_html}</p>"
            "</ac:rich-text-body>"
            "</ac:structured-macro>"
            f"<h2>Problema</h2><p>{esc(article.problem)}</p>"
            f"<h2>Causa raiz</h2><p>{esc(article.cause)}</p>"
            f"<h2>Solução</h2><ol>{steps}</ol>"
            f"{faq_block}"
            "<h2>Metadados</h2>"
            "<table><tbody>"
            f"<tr><td><strong>Total de tickets</strong></td><td>{cluster.count}</td></tr>"
            f"<tr><td><strong>Componentes</strong></td>"
            f"<td>{esc(', '.join(cluster.components)) or '—'}</td></tr>"
            f"<tr><td><strong>Labels</strong></td>"
            f"<td>{esc(', '.join(cluster.labels)) or '—'}</td></tr>"
            f"<tr><td><strong>Tags</strong></td>"
            f"<td>{esc(', '.join(article.tags)) or '—'}</td></tr>"
            "</tbody></table>"
            f"{CONFLUENCE_FOOTER}"
        )
