"""Cliente HTTP para Jira Cloud (REST v3). Pagina, normaliza ADF, retry.

Usa o endpoint `/rest/api/3/search/jql` (novo) com paginação por `nextPageToken`.
O antigo `/rest/api/3/search` foi descontinuado pela Atlassian em 2025.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kiro.domain.exceptions import JiraError
from kiro.domain.models import Ticket
from kiro.utils.adf import extract_text_from_adf

log = logging.getLogger(__name__)

_FIELDS = "summary,description,labels,components,status,resolutiondate"


class JiraClient:
    def __init__(
        self,
        base_url: str,
        user_email: str,
        api_token: str,
        timeout_seconds: int = 30,
        page_size: int = 100,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (user_email, api_token)
        self._timeout = timeout_seconds
        self._page_size = page_size

    def search_closed(
        self,
        project_key: str,
        closed_statuses: list[str],
        lookback_days: int,
        extra_jql: Optional[str] = None,
    ) -> list[Ticket]:
        jql = self._build_jql(project_key, closed_statuses, lookback_days, extra_jql)
        log.info("jira: JQL = %s", jql)
        tickets = [self._to_ticket(issue) for issue in self._paginate(jql)]
        log.info("jira: %d tickets coletados (lookback=%dd)", len(tickets), lookback_days)
        return tickets

    @staticmethod
    def _build_jql(
        project_key: str,
        statuses: list[str],
        lookback_days: int,
        extra: Optional[str],
    ) -> str:
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        status_list = ", ".join(f'"{s}"' for s in statuses) or '"Done"'
        parts = [
            f'project = "{project_key}"',
            f"status in ({status_list})",
            f'updated >= "{since}"',
        ]
        if extra:
            parts.append(f"({extra})")
        return " AND ".join(parts) + " ORDER BY updated DESC"

    def _paginate(self, jql: str) -> Iterator[dict]:
        """Paginação por nextPageToken (endpoint /search/jql).

        O novo endpoint não retorna mais `total`; quebramos quando `nextPageToken`
        não vem na resposta (e/ou `isLast=true`).
        """
        next_token: Optional[str] = None
        with httpx.Client(auth=self._auth, timeout=self._timeout) as client:
            while True:
                data = self._fetch_page(client, jql, next_token)
                issues = data.get("issues", []) or []
                yield from issues
                next_token = data.get("nextPageToken")
                is_last = data.get("isLast")
                if not next_token or is_last:
                    return

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    def _fetch_page(
        self,
        client: httpx.Client,
        jql: str,
        next_token: Optional[str],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": self._page_size,
            "fields": _FIELDS,
        }
        if next_token:
            params["nextPageToken"] = next_token
        try:
            resp = client.get(
                f"{self._base_url}/rest/api/3/search/jql",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "")[:200]
            log.error("jira HTTP %s: %s", e.response.status_code, body)
            raise JiraError(
                f"busca no Jira falhou: {e.response.status_code}"
            ) from e

    @staticmethod
    def _to_ticket(issue: dict) -> Ticket:
        fields = issue.get("fields", {}) or {}
        description = extract_text_from_adf(fields.get("description"))
        resolved_raw = fields.get("resolutiondate")
        resolved_dt: Optional[datetime] = None
        if isinstance(resolved_raw, str):
            try:
                resolved_dt = datetime.fromisoformat(resolved_raw.replace("Z", "+00:00"))
            except ValueError:
                resolved_dt = None
        return Ticket(
            key=issue.get("key", ""),
            summary=fields.get("summary") or "",
            description=description,
            labels=fields.get("labels") or [],
            components=[c.get("name", "") for c in (fields.get("components") or []) if c],
            status=(fields.get("status") or {}).get("name"),
            resolved_at=resolved_dt,
        )
