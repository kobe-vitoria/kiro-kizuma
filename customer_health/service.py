import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from customer_health.jira_client import CustomerJiraClient
from customer_health.llm import generate_friendly_assessment
from customer_health.settings import RelationshipSettings
from customer_health.temperature import RelationshipTemperature, compute_relationship_temperature


@dataclass(frozen=True)
class RelationshipReport:
    customer_name: str
    jql_used: str
    generated_at: str
    temperature: RelationshipTemperature
    assessment_text: str
    output_markdown: Path
    output_json: Path


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "cliente"


def _sanitize_host_tokens(base_url: str) -> list[str]:
    host = urlparse(base_url).hostname or ""
    parts = [p for p in host.split(".") if p and p not in {"www", "atlassian", "net", "com", "io", "org"}]
    return parts


def _build_payload(
    *,
    customer_name: str,
    jql: str,
    temperature: RelationshipTemperature,
    sampled_tickets: list[dict],
) -> dict:
    sla_total = sum(int(item.get("sla_targets_total", 0)) for item in sampled_tickets)
    sla_breached = sum(int(item.get("sla_targets_breached", 0)) for item in sampled_tickets)
    sla_met = sum(int(item.get("sla_targets_met", 0)) for item in sampled_tickets)
    return {
        "cliente": "[CLIENTE]",
        "jql_contexto": jql.replace(customer_name, "[CLIENTE]"),
        "indicadores": asdict(temperature),
        "sla_resumo": {
            "targets_total_amostra": sla_total,
            "targets_breach_amostra": sla_breached,
            "targets_ok_amostra": sla_met,
        },
        "amostra_tickets": sampled_tickets,
        "nota": "Os dados de ticket foram minimizados para evitar exposição de nomes de empresa.",
    }


def _resolve_time_window(
    *,
    settings: RelationshipSettings,
    lookback_days: int | None,
    lookback_months: int | None,
    all_history: bool | None,
) -> tuple[str, int, int, bool]:
    if all_history is None:
        all_history = settings.all_history

    if lookback_months is None:
        lookback_months = settings.lookback_months

    if lookback_days is None:
        lookback_days = settings.lookback_days

    if all_history:
        return "", 0, 0, True

    if lookback_months and lookback_months > 0:
        days = lookback_months * 30
        return f"AND updated >= -{days}d ", days, lookback_months, False

    if lookback_days and lookback_days > 0:
        return f"AND updated >= -{lookback_days}d ", lookback_days, 0, False

    # Sem valor explícito => sem limite.
    return "", 0, 0, True


def run_relationship_analysis(
    settings: RelationshipSettings,
    *,
    customer_name: str,
    lookback_days: int | None = None,
    lookback_months: int | None = None,
    all_history: bool | None = None,
    ticket_limit: int | None = None,
) -> RelationshipReport:
    time_clause, effective_days, effective_months, using_all_history = _resolve_time_window(
        settings=settings,
        lookback_days=lookback_days,
        lookback_months=lookback_months,
        all_history=all_history,
    )
    limit = ticket_limit or settings.ticket_limit

    jql = settings.customer_jql_template.format(
        project_key=settings.jira_project_key,
        customer_name=customer_name,
        lookback_days=effective_days,
        lookback_months=effective_months,
        time_clause=time_clause,
    )

    jira = CustomerJiraClient(
        base_url=settings.jira_base_url,
        user_email=settings.jira_user_email,
        api_token=settings.jira_api_token.get_secret_value(),
        timeout_seconds=settings.jira_timeout_seconds,
        page_size=settings.jira_page_size,
    )
    tickets = jira.fetch_customer_tickets(jql=jql, limit=limit)
    temperature = compute_relationship_temperature(tickets)

    total_sla_targets = sum(t.sla_targets_total for t in tickets)
    total_sla_breached = sum(t.sla_targets_breached for t in tickets)
    total_sla_met = sum(t.sla_targets_met for t in tickets)

    compact_sample = [
        {
            "key": t.key,
            "status": t.status,
            "priority": t.priority,
            "created": t.created,
            "updated": t.updated,
            "resolution_date": t.resolution_date,
            "sla_breached": t.sla_breached,
            "sla_targets_total": t.sla_targets_total,
            "sla_targets_breached": t.sla_targets_breached,
            "sla_targets_met": t.sla_targets_met,
            "sla_details": t.sla_details[:3],
            "summary_has_risk_markers": any(
                marker in (t.summary or "").lower()
                for marker in ("erro", "falha", "urgente", "indispon", "reclama", "lento")
            ),
        }
        for t in tickets[:15]
    ]

    payload = _build_payload(
        customer_name=customer_name,
        jql=jql,
        temperature=temperature,
        sampled_tickets=compact_sample,
    )
    payload["sla_resumo"]["targets_total_global"] = total_sla_targets
    payload["sla_resumo"]["targets_breach_global"] = total_sla_breached
    payload["sla_resumo"]["targets_ok_global"] = total_sla_met

    company_tokens = _sanitize_host_tokens(settings.jira_base_url)
    if temperature.ticket_count == 0:
        if using_all_history:
            window_hint = "sem limite temporal"
        elif effective_months > 0:
            window_hint = f"janela de {effective_months} mes(es)"
        else:
            window_hint = f"janela de {effective_days} dia(s)"
        assessment_text = (
            "Não encontrei tickets suficientes para este cliente no período informado. "
            f"Revise o nome usado no Jira, a configuração da janela ({window_hint}) "
            "ou ajuste REL_CUSTOMER_JQL_TEMPLATE."
        )
    else:
        assessment_text = generate_friendly_assessment(
            settings,
            customer_name=customer_name,
            company_tokens=company_tokens,
            payload=payload,
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    output_root = settings.output_dir
    output_root.mkdir(parents=True, exist_ok=True)

    slug = _slug(customer_name)
    md_path = output_root / f"{slug}_relacionamento.md"
    json_path = output_root / f"{slug}_relacionamento.json"

    md_path.write_text(
        "\n".join(
            [
                f"# Kizuma — Diagnóstico de relacionamento", 
                "",
                f"Cliente analisado: {customer_name}",
                f"Gerado em: {generated_at}",
                f"Tickets analisados: {temperature.ticket_count}",
                f"Temperatura: {temperature.level} (score={temperature.score})",
                f"Status da relação: {temperature.quality_status}",
                "",
                "## Análise amigável (Kizuma Healthcheck)",
                "",
                assessment_text,
            ]
        ),
        encoding="utf-8",
    )

    json_payload = {
        "customer_name": customer_name,
        "generated_at": generated_at,
        "jql_used": jql,
        "temperature": asdict(temperature),
        "assessment_text": assessment_text,
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return RelationshipReport(
        customer_name=customer_name,
        jql_used=jql,
        generated_at=generated_at,
        temperature=temperature,
        assessment_text=assessment_text,
        output_markdown=md_path,
        output_json=json_path,
    )
