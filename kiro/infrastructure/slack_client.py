"""Cliente para webhooks do Slack."""

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kiro.domain.exceptions import SlackError
from kiro.domain.models import PublishResult

log = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, webhook_url: str, timeout_seconds: int = 15) -> None:
        if not webhook_url:
            raise SlackError("SLACK_WEBHOOK_URL vazio.")
        self._webhook_url = webhook_url
        self._timeout = timeout_seconds

    def notify(self, results: list[PublishResult]) -> None:
        if not results:
            log.info("slack: nada a notificar")
            return
        self._post({"text": self._format_message(results)})

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    def _post(self, payload: dict) -> None:
        try:
            resp = httpx.post(self._webhook_url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            log.info("slack: mensagem enviada")
        except httpx.HTTPStatusError as e:
            raise SlackError(f"Slack retornou {e.response.status_code}") from e

    @staticmethod
    def _format_message(results: list[PublishResult]) -> str:
        ok = [r for r in results if r.succeeded]
        failed = [r for r in results if not r.succeeded]
        lines = [
            "*KIRO — análise de tickets concluída*",
            f"Clusters: *{len(results)}*  |  sucesso: *{len(ok)}*  |  falhas: *{len(failed)}*",
            "",
            "Tópicos processados:",
        ]
        for i, r in enumerate(results, 1):
            mark = ":large_green_circle:" if r.succeeded else ":red_circle:"
            location = r.confluence_url or r.local_path or "—"
            lines.append(
                f"{mark} *{i}. {r.article_title}* — {r.ticket_count} tickets — `{location}`"
            )
        return "\n".join(lines)
