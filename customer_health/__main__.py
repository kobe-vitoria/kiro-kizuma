import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from customer_health.service import run_relationship_analysis
from customer_health.settings import RelationshipSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kizuma",
        description="Kizuma Healthcheck — diagnóstico amigável de relacionamento cliente-suporte",
    )
    parser.add_argument(
        "--customer-name",
        type=str,
        default="",
        help="Nome do cliente como aparece no Jira",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Janela retroativa em dias (sobrescreve REL_LOOKBACK_DAYS)",
    )
    parser.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Janela retroativa em meses (prioridade sobre dias)",
    )
    parser.add_argument(
        "--all-history",
        action="store_true",
        help="Analisa histórico completo (ignora dias/meses)",
    )
    parser.add_argument(
        "--ticket-limit",
        type=int,
        default=None,
        help="Máximo de tickets analisados (sobrescreve REL_TICKET_LIMIT)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Arquivo env alternativo para este app (ex.: .env.customer_health)",
    )
    return parser


def _read_customer_name(initial: str) -> str:
    if initial.strip():
        return initial.strip()
    try:
        value = input("Nome do cliente (como está no Jira): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    return value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.env_file:
            settings = RelationshipSettings(_env_file=str(args.env_file))
        else:
            settings = RelationshipSettings()
    except ValidationError as exc:
        print("[kizuma] configuração inválida:", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(
            "[hint] copie .env.customer_health.example para .env.customer_health e preencha os campos",
            file=sys.stderr,
        )
        return 2

    customer_name = _read_customer_name(args.customer_name)
    if not customer_name:
        print("[kizuma] nome do cliente não informado", file=sys.stderr)
        return 2

    try:
        report = run_relationship_analysis(
            settings,
            customer_name=customer_name,
            lookback_days=args.lookback_days,
            lookback_months=args.lookback_months,
            all_history=args.all_history,
            ticket_limit=args.ticket_limit,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[kizuma] falha na análise: {exc}", file=sys.stderr)
        return 1

    print("\n=== Kizuma Healthcheck ===\n")
    print(report.assessment_text)
    print("\n----------------------------------------------")
    print(f"Temperatura: {report.temperature.level} (score={report.temperature.score})")
    print(f"Status da relação: {report.temperature.quality_status}")
    print(f"Tickets analisados: {report.temperature.ticket_count}")
    print(f"Relatório markdown: {report.output_markdown}")
    print(f"Relatório JSON: {report.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
