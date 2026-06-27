# Customer Relationship Health (app paralelo)

## Objetivo

Criar uma estrutura paralela ao KIRO para diagnosticar a qualidade da relação
cliente-suporte a partir dos tickets recentes no Jira, com saída amigável para
público não técnico e sem expor nomes de empresa.

## Fluxo

1. Usuário informa nome do cliente e credenciais via env/secrets.
2. App busca os últimos N tickets relevantes no Jira.
3. App calcula uma "temperatura" (score e nível).
4. IA (Gemini/Anthropic) gera diagnóstico em linguagem amigável.
5. Relatório final é salvo em markdown/json e exibido no terminal/GitHub Actions.

## Arquivos principais

- customer_health/__main__.py
- customer_health/settings.py
- customer_health/jira_client.py
- customer_health/temperature.py
- customer_health/llm.py
- customer_health/service.py
- .env.customer_health.example
- .github/workflows/customer-relationship-health.yml

## Restrições atendidas

- Não altera o fluxo existente do KIRO.
- Não expõe nome da empresa no output final (redação e prompt com regra explícita).
- Permite uso local e via GitHub Actions (workflow_dispatch).
