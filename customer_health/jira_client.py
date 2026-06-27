from dataclasses import dataclass
from typing import Any, Optional

import httpx

from kiro.utils.adf import extract_text_from_adf


@dataclass(frozen=True)
class CustomerTicket:
    key: str
    status: str
    priority: str
    created: str
    updated: str
    resolution_date: str
    summary: str
    description: str
    sla_breached: bool
    sla_targets_total: int
    sla_targets_breached: int
    sla_targets_met: int
    sla_details: list[dict[str, Any]]


class CustomerJiraClient:
    def __init__(
        self,
        *,
        base_url: str,
        user_email: str,
        api_token: str,
        timeout_seconds: int,
        page_size: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (user_email, api_token)
        self._timeout = timeout_seconds
        self._page_size = page_size

    def fetch_customer_tickets(self, *, jql: str, limit: int) -> list[CustomerTicket]:
        tickets: list[CustomerTicket] = []
        next_token: Optional[str] = None
        names: dict[str, str] = {}

        with httpx.Client(auth=self._auth, timeout=self._timeout) as client:
            while len(tickets) < limit:
                payload = self._fetch_page(client, jql, next_token)
                names.update(payload.get("names") or {})
                issues = payload.get("issues", []) or []
                for issue in issues:
                    tickets.append(self._to_ticket(issue, names))
                    if len(tickets) >= limit:
                        break

                next_token = payload.get("nextPageToken")
                if not next_token:
                    break

        return tickets

    def _fetch_page(
        self,
        client: httpx.Client,
        jql: str,
        next_token: Optional[str],
    ) -> dict[str, Any]:
        fields = "*all"
        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": self._page_size,
            "fields": fields,
            "expand": "names",
        }
        if next_token:
            params["nextPageToken"] = next_token

        response = client.get(f"{self._base_url}/rest/api/3/search/jql", params=params)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_sla_details(
        fields: dict[str, Any],
        names: dict[str, str],
    ) -> tuple[bool, int, int, int, list[dict[str, Any]]]:
        details: list[dict[str, Any]] = []
        total = 0
        breached = 0
        met = 0

        for field_key, value in fields.items():
            field_name = names.get(field_key, field_key)
            if "sla" not in field_name.lower() and "sla" not in field_key.lower():
                continue

            if not isinstance(value, dict):
                continue

            cycles = value.get("completedCycles") or []
            ongoing = value.get("ongoingCycle")
            target_name = str(value.get("name") or field_name)

            target_total = 0
            target_breached = 0
            target_met = 0

            if isinstance(cycles, list):
                for cycle in cycles:
                    if not isinstance(cycle, dict):
                        continue
                    target_total += 1
                    if bool(cycle.get("breached")):
                        target_breached += 1
                    else:
                        target_met += 1

            if isinstance(ongoing, dict):
                # Conta ciclo em aberto também como target em andamento.
                target_total += 1
                if bool(ongoing.get("breached")):
                    target_breached += 1

            if target_total == 0 and "breached" in value:
                target_total = 1
                if bool(value.get("breached")):
                    target_breached = 1
                else:
                    target_met = 1

            if target_total == 0:
                continue

            details.append(
                {
                    "target": target_name,
                    "total_cycles": target_total,
                    "breached_cycles": target_breached,
                    "met_cycles": target_met,
                }
            )

            total += target_total
            breached += target_breached
            met += target_met

        return breached > 0, total, breached, met, details

    @classmethod
    def _to_ticket(cls, issue: dict[str, Any], names: dict[str, str]) -> CustomerTicket:
        fields = issue.get("fields", {}) or {}
        description_raw = fields.get("description")
        if isinstance(description_raw, dict):
            description = extract_text_from_adf(description_raw)
        elif isinstance(description_raw, str):
            description = description_raw
        else:
            description = ""

        (
            sla_breached,
            sla_targets_total,
            sla_targets_breached,
            sla_targets_met,
            sla_details,
        ) = cls._extract_sla_details(fields, names)

        return CustomerTicket(
            key=issue.get("key", ""),
            status=((fields.get("status") or {}).get("name") or "").strip(),
            priority=((fields.get("priority") or {}).get("name") or "").strip(),
            created=str(fields.get("created") or ""),
            updated=str(fields.get("updated") or ""),
            resolution_date=str(fields.get("resolutiondate") or ""),
            summary=str(fields.get("summary") or ""),
            description=description,
            sla_breached=sla_breached,
            sla_targets_total=sla_targets_total,
            sla_targets_breached=sla_targets_breached,
            sla_targets_met=sla_targets_met,
            sla_details=sla_details,
        )
