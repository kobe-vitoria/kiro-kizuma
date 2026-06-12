# KIRO — Documentação Completa

> Automação que transforma centenas de tickets repetidos em rascunhos de
> artigos cliente-facing, com grounding em docs Kobe oficiais e proteção
> determinística contra vazamento de contexto interno.

**Versão:** 1.1.0
**Stack:** Python 3.11+ · Pydantic · httpx · Gemini AI · Jira REST API v3 · Confluence Cloud · GitBook
**Mantenedor:** Matheus Silva — time de Suporte / Kobe

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [O problema que resolve](#2-o-problema-que-resolve)
3. [Como funciona — fluxo de alto nível](#3-como-funciona)
3.5 [**V1.1 — Grounding, Style Reference e Linter**](#35-v11--grounding-style-reference-e-linter)
4. [Critérios de aceite vs entrega](#4-critérios-de-aceite-vs-entrega)
5. [Arquitetura](#5-arquitetura)
6. [Stack técnica](#6-stack-técnica)
7. [Pipeline em detalhes](#7-pipeline-em-detalhes)
8. [Provedores de LLM](#8-provedores-de-llm)
9. [CLI — comandos e flags](#9-cli)
10. [Configuração — todas as variáveis](#10-configuração)
11. [Artefatos de saída](#11-artefatos-de-saída)
12. [Segurança](#12-segurança)
13. [Resiliência e tratamento de erros](#13-resiliência)
14. [Testes](#14-testes)
15. [Setup & operação](#15-setup-e-operação)
16. [Métricas observadas no projeto OPE](#16-métricas-observadas)
17. [Roadmap](#17-roadmap)
18. [Glossário](#18-glossário)
19. [Troubleshooting](#19-troubleshooting)
20. [Apêndice — árvore do projeto](#20-árvore-completa-do-projeto)

---

## 1. Visão geral

**KIRO** (Knowledge Inferred from Recurring tIckets and Observations) é uma automação Python que executa periodicamente sobre a base de tickets fechados do Jira, identifica padrões de problemas repetidos, e gera **rascunhos completos de artigos de Knowledge Base** usando IA generativa (Google Gemini).

Os rascunhos são salvos localmente em formato Markdown e, opcionalmente, publicados como páginas em rascunho no Confluence para o time de documentação revisar e publicar. Uma notificação opcional pode ser enviada ao Slack avisando que há material novo para revisão.

### Para quem é

- **Gestor de Suporte (você)** — reduz o backlog de "dúvidas repetidas dos clientes"
- **Time de Documentação** — ganha rascunhos prontos para revisar, em vez de começar do zero
- **Time de Suporte** — vai poder linkar artigos novos para responder dúvidas recorrentes mais rápido

### Estado atual (V1.1)

- ✅ Integração com Jira funcionando (708 tickets coletados na rodada real de 2026-06-12)
- ✅ Clusterização funcionando (top 5 clusters mais frequentes por rodada)
- ✅ Geração de artigos via Gemini funcionando (qualidade comercial em PT-BR, 2 estilos: Artigo / FAQ)
- ✅ **RAG GitBook público** — 1146 chunks indexados, injetados no prompt como grounding factual (issue #3)
- ✅ **Confluence SUP como style reference** — 1554 chunks de 324 artigos publicados, few-shot calibra o tom + dedupe sinaliza tópicos já cobertos (issue #10)
- ✅ **Linter pós-geração** — 10 regras determinísticas bloqueiam vazamento (códigos OPE-, jargão técnico, URLs internas, código) antes do save (issue #12)
- ✅ Salvamento local de artefatos em 4 pastas: `drafts/` (Artigo md), `docs/` (Artigo docx), `faqs_md/` (FAQ md), `faqs_docx/` (FAQ docx)
- ✅ Suite de **296 testes** passando
- ⏳ Publicação no Confluence — código pronto, esperando liberação de permissão de "Create Page" no space `AAC`
- ⏳ Notificação no Slack — código pronto, esperando decisão sobre canal

---

## 2. O problema que resolve

### Antes do KIRO

O time de Suporte da Kobe (projeto **OPE** no Jira) recebe centenas de tickets por mês. Muitas dúvidas são **recorrentes** — variações do mesmo problema sobre deeplink quebrado, exibição de serviços na Epharma, performance de listas, etc.

Sem KIRO:
- O time de Doc precisa **garimpar manualmente** os tickets para identificar padrões
- Cada artigo de KB exige **horas de análise** + **horas de escrita**
- Vários problemas recorrentes **nunca viram documentação** por falta de tempo
- Clientes continuam abrindo tickets sobre o mesmo problema → suporte é sobrecarregado

### Depois do KIRO

Uma vez por mês (ou sob demanda), o KIRO:
1. Puxa todos os tickets fechados do mês
2. Identifica os **5 a 10 temas mais recorrentes** automaticamente
3. Gera **rascunhos completos** em PT-BR com problema / causa / solução / FAQ
4. Salva localmente + publica como **draft no Confluence**
5. Avisa o time no Slack que tem material pra revisar

O time de doc abre os drafts, ajusta o que precisar e publica. **Trabalho de semanas vira trabalho de horas.**

### ROI estimado (a confirmar com a chefe)

Se cada artigo manual exige ~4 horas de análise + escrita, e KIRO gera 5 drafts em ~30 segundos:

| Métrica | Manual | Com KIRO |
|---|---|---|
| Tempo para 5 artigos | ~20 horas | ~30 segundos + revisão (~2-4h) |
| Custo de IA (Gemini) | — | ~$0.001 por rodada |
| Conhecimento perdido | Alto (vários temas nunca viram artigo) | Baixo (todos os top-N viram rascunho) |

---

## 3. Como funciona

### Fluxo em alto nível

```
   ┌──────────┐    ┌────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Jira API │ →  │ Clustering │ →  │ LLM (Gemini) │ →  │ output/      │ →  │ Confluence + │
   │ (REST v3)│    │ heurístico │    │ draft JSON   │    │ md, json,    │    │ Slack (opt)  │
   └──────────┘    └────────────┘    └──────────────┘    │ report       │    └──────────────┘
                                                         └──────────────┘
   fetch            cluster            generate           persist            publish + notify
```

### Passo a passo

1. **Fetch** — Conecta ao Jira via REST API v3, autenticando com Basic Auth (email + API token). Roda uma JQL parametrizada (`project = "OPE" AND status in (Done, Closed, Resolved) AND updated >= <30d>`) e pagina os resultados via `nextPageToken` até pegar todos os tickets fechados do período.

2. **Normalização** — Extrai texto de `description` (que vem em ADF — Atlassian Document Format) recursivamente, limpa whitespace, tokeniza removendo stop-words em PT/EN.

3. **Cluster** — Aplica estratégia heurística (TF-DF + bigramas com filtro de termos universais) para agrupar tickets que compartilham vocabulário relevante. Retorna os top N clusters (default 5) ordenados por número de tickets.

4. **Generate** — Para cada cluster, monta um prompt estruturado com o tópico + 5 exemplos de tickets + labels + componentes, manda para o Gemini (`gemini-2.5-flash-lite`), exige resposta JSON com schema fixo (title, problem, cause, solution, faq, tags), valida via Pydantic.

5. **Persist** — Salva tudo localmente:
   - `output/tickets.json` — tickets coletados (auditoria)
   - `output/clusters.json` — clusters detectados
   - `output/articles.json` — artigos completos (cluster + draft)
   - `output/drafts/*.md` — cada artigo como Markdown bonito
   - `output/errors.json` — falhas por etapa
   - `output/report.md` — relatório executivo

6. **Publish (opcional)** — Se `--publish-confluence` ou `ENABLE_CONFLUENCE_PUBLISH=true`, converte cada draft em Confluence Storage Format (HTML), cria página em status `draft` no space configurado, retorna URL.

7. **Notify (opcional)** — Se `--notify-slack` ou `ENABLE_SLACK_NOTIFY=true`, envia mensagem formatada ao webhook Slack com lista dos artigos gerados + URLs.

---

## 3.5 V1.1 — Grounding, Style Reference e Linter

A V1.0 já gerava artigos via Jira + Gemini. A V1.1 **eleva a qualidade** em três eixos independentes, todos opcionais (default OFF) e que **não conflitam com a V1.0** — desligando as flags, comportamento é idêntico.

### Fluxo enriquecido

```
                            ┌────────────────┐
                            │ GitBook público│ (grounding factual)
                            │ 1146 chunks    │
                            └───────┬────────┘
                                    │ TF-IDF
                                    ▼
┌──────────┐   ┌──────────┐   ┌──────────────────┐   ┌─────────┐   ┌──────────┐
│ Jira API │ → │ Cluster  │ → │ Prompt enriquecido│ → │ Linter  │ → │ output/  │
└──────────┘   └──────────┘   └──────────────────┘   │ BLOCK + │   └──────────┘
                                    ▲                │ WARN    │
                                    │                └─────────┘
                            ┌───────┴────────┐
                            │ Confluence SUP │ (style reference + dedupe)
                            │ 1554 chunks    │
                            └────────────────┘
```

### Os três eixos

#### Eixo 1: RAG GitBook (issue #3)

**O que é**: KIRO baixa a GitBook pública da Kobe (`https://kobeapps.gitbook.io/kobe.io-documentacao`), chunkea por seção (h1/h2/h3, ~800 chars), e indexa via TF-IDF local. Pra cada cluster, os top-K chunks mais similares são injetados no prompt como bloco `REFERÊNCIA KOBE`.

**Por que importa**: o LLM ganha grounding factual sobre como o produto Kobe realmente funciona — reduz alucinação ("o cliente pode fazer X" quando X não existe).

**Política**: artigos **NUNCA citam** URLs do GitBook no output. É grounding interno, não fonte citável. O bloco no prompt inclui regra explícita "NÃO inclua URLs de origem".

**Como ativar**: `ENABLE_GITBOOK_RAG=true` no `.env`. Cache em `kiro/data/gitbook_public_cache.json` (gerado via `kiro fetch-gitbook --public`).

#### Eixo 2: Confluence SUP como style reference + dedupe (issue #10)

**O que é**: KIRO baixa todos os artigos publicados no space SUP do Confluence (324 páginas válidas após filtro de meta-páginas) e usa de duas formas:

1. **Style reference (few-shot)** — top-K artigos mais similares são injetados no prompt como bloco `EXEMPLOS DO ESTILO KOBE`. O LLM imita o tom, estrutura ("Visão Geral", "Cloud Commerce e Integrações", "Perguntas Frequentes") e vocabulário ("Master Data", "sistemas envolvidos") que já foi aprovado em produção.
2. **Dedupe** — se algum artigo SUP tem cosine ≥ `CONFLUENCE_DEDUPE_THRESHOLD` com o cluster, KIRO sinaliza no footer: `⚠ 1 cluster(s) com artigo similar em SUP — considere atualizar em vez de criar novo`.

**Política**: artigos **NUNCA mencionam** os exemplos no output. As 3 regras absolutas do bloco: "NÃO copie o conteúdo", "NÃO mencione esses exemplos", "NÃO inclua URLs".

**Como ativar**: `ENABLE_CONFLUENCE_FEW_SHOT=true`. Cache em `kiro/data/confluence_sup_cache.json` (gerado via `kiro fetch-confluence-kb`).

#### Eixo 3: Output Linter (issue #12)

**O que é**: validador determinístico que roda **depois** do LLM gerar o draft e **antes** do save. Não confia 100% no prompt — verifica regra a regra.

**Regras BLOCK (não salva, marca como erro)**:
- `no_ope_codes` — códigos `OPE-\d+` no corpo do artigo
- `no_internal_jargon` — "bug", "workaround", "regressão", "root cause", "causa raiz", "hotfix", "stack trace"
- `no_internal_components` — "WebView", "SDK Connect", "Mobile Connect"
- `no_team_references` — "time interno", "nosso backlog", "nossa engenharia", "nosso time"
- `no_external_urls` — hosts `gitbook.io`, `atlassian.net`, `kobeapps.gitbook`, `confluence.kobe`
- `no_code_or_trace` — blocos de código (` ``` `), HTML `<code>`, padrão de stack trace

**Regras WARN (salva mas reporta)**:
- `generic_phrases` — "verifique as configurações", "limpe o cache", "tente novamente", "entre em contato com o suporte"
- `field_too_short` — `problem < 50`, `cause < 30`, `solution < 100`, `intro < 40` chars
- `solution_step_count` — solução com menos de 4 passos
- `faq_entries_count` — FAQ com menos de 5 entries

**Modos** (`LINTER_BLOCK_MODE`):
- `skip` (default) — pula cluster com block, segue rodada
- `fail` — derruba a rodada inteira no primeiro block
- `warn` — salva mesmo com block, só registra pra revisor

**Como ativar**: `ENABLE_OUTPUT_LINTER=true`.

**Exemplo real (rodada de 2026-06-12)**:
```
🛡  Linter: 1 bloqueado(s), 2 com warning(s)
  ✗ 'QA: Execução dos testes' — 1 violação(ões)
    [entries.0.answer] componente interno 'WebView' não deve aparecer
```

LLM tentou usar "WebView" numa resposta da FAQ — o linter bloqueou o save. Sem ele, esse documento iria pro `drafts/` com vazamento.

### Resumo: o que muda no output

| Aspecto | V1.0 | V1.1 |
|---|---|---|
| Fonte de contexto | Só tickets do Jira | Tickets + GitBook + Confluence SUP |
| Calibração de tom | Prompt detalhado | Prompt + few-shot de artigos reais |
| Vazamento de jargão | Mitigado pelo prompt | Mitigado pelo prompt **+ bloqueado pelo linter** |
| Sinalização de duplicata | — | Dedupe contra SUP no footer |
| Compatibilidade V1.0 | — | 100% — todas as flags têm default OFF |

---

## 4. Critérios de aceite vs entrega

A task original da chefe (em `task.md`):

| Critério | Status | Como o KIRO atende |
|---|---|---|
| Script roda mensalmente sobre tickets fechados | ✅ Pronto | `LOOKBACK_DAYS=30`, agendamento via GitHub Actions cron `0 11 1 * *` (dia 1 do mês 08:00 BRT) |
| Identifica clusters de repetição | ✅ Pronto | Heurística TF-DF + bigramas. Top 5 por rodada por default |
| Gera página draft no Confluence com estrutura mapeada | ⏳ Pronto, aguardando permissão | Código completo em `kiro/infrastructure/confluence_client.py`. Cria página `status=draft` no space `AAC` |
| Notifica time via Slack/E-mail | ⏳ Pronto, aguardando decisão | Código completo em `kiro/infrastructure/slack_client.py`. Aguardando canal de destino |

### Adicionais V1.1 (além do escopo original)

| Funcionalidade | Status | Detalhe |
|---|---|---|
| Output em dois estilos (Artigo + FAQ self-service B2B) | ✅ Pronto | `kiro run --style artigo\|faq` ou prompt interativo |
| Exportação `.docx` automática | ✅ Pronto | Output em `output/docs/` e `output/faqs_docx/` — abre em Word/Pages/Drive |
| Grounding via GitBook público | ✅ Pronto | Issue #3 — `ENABLE_GITBOOK_RAG=true` |
| Style reference via Confluence SUP | ✅ Pronto | Issue #10 — `ENABLE_CONFLUENCE_FEW_SHOT=true` |
| Dedupe contra artigos existentes | ✅ Pronto | Issue #10 — sinalizado no footer |
| Proteção contra vazamento (linter) | ✅ Pronto | Issue #12 — `ENABLE_OUTPUT_LINTER=true` |

---

## 5. Arquitetura

### Princípios

- **Clean Architecture em 4 camadas** — dependências apontam sempre para dentro
- **Estratégias plugáveis** via interfaces (ABC) — trocar clustering ou LLM sem tocar no domínio
- **Configuração 100% externa** — nenhum valor de negócio hardcoded no código
- **Fail-fast** — settings inválidas abortam na inicialização, antes de queimar API
- **Pipeline por estágios** — pode rodar parcial (`--stage fetch|cluster|generate|publish|notify`)

### Diagrama de camadas

```
┌───────────────────────────────────────────────────────────────┐
│  interfaces/        (CLI argparse — único entrypoint humano)  │
└──────┬────────────────────────────────────────────────────────┘
       │ usa
┌──────▼────────────────────────────────────────────────────────┐
│  application/                                                 │
│    pipeline.py        (orquestrador — chama estágios)         │
│    clustering/        (estratégias plugáveis: heuristic)      │
│    generation/                                                │
│      ├ base.py / factory.py                                   │
│      ├ gemini_provider.py / anthropic_provider.py / mock      │
│      ├ kb_context.py        (helper bloco "REFERÊNCIA KOBE")  │
│      └ style_examples.py    (helper bloco "EXEMPLOS ESTILO")  │
│    retrieval.py        (KnowledgeRetriever — TF-IDF GitBook)  │
│    style_reference.py  (StyleReferenceFinder — SUP + dedupe)  │
│    lint.py             (OutputLinter — engine)                │
│    lint_rules.py       (regras BLOCK + WARN + registries)     │
│    normalization.py    (tokenize, normalize_text)             │
└──────┬────────────────────────────────────────────────────────┘
       │ depende
┌──────▼────────────────────────────────────────────────────────┐
│  domain/                                                      │
│    models.py          (Ticket, Cluster, ArticleDraft, etc.)   │
│    exceptions.py      (KiroError + subclasses)                │
└───────────────────────────────────────────────────────────────┘
       ▲
       │ implementa
┌──────┴────────────────────────────────────────────────────────┐
│  infrastructure/     (clientes HTTP + persistência)           │
│    jira_client.py          (Jira REST v3, paginação)          │
│    confluence_client.py    (Confluence Cloud, Storage Format) │
│    confluence_kb_loader.py (SUP scraper — issue #10)          │
│    gitbook_loader.py       (GitBook scraper — issue #2/#3)    │
│    slack_client.py         (webhooks)                         │
│    docx_exporter.py        (python-docx)                      │
│    persistence.py          (ArtifactStore — JSON + md + docx) │
└───────────────────────────────────────────────────────────────┘

       ┌─────────────────────────────────────────────────────┐
       │  config/      (Settings — pydantic-settings)        │
       │  utils/       (logging, branding, progress,         │
       │                adf, adf_to_markdown)                │
       └─────────────────────────────────────────────────────┘
              ↑ usado por todas as camadas
```

### Responsabilidades por camada

| Camada | Responsabilidade | Conhece |
|---|---|---|
| `domain/` | Modelos imutáveis de negócio (`Ticket`, `Cluster`, `ArticleDraft`) e exceções | Nada externo |
| `application/` | Casos de uso (orquestração do pipeline) + interfaces de estratégia | Domain + interfaces ABC |
| `infrastructure/` | Clientes HTTP, persistência em filesystem, implementações concretas | httpx, APIs externas, Pydantic |
| `interfaces/cli.py` | CLI argparse — único ponto de invocação humano | Tudo, via injeção de dependência |
| `config/` | `Settings` Pydantic, validação fail-fast, defaults por provedor | Env + `.env` |
| `utils/` | Helpers transversais: ADF parser, logging com redação, branding visual, progress spinner | stdlib |

---

## 6. Stack técnica

### Por que cada escolha

| Tecnologia | Versão | Por que |
|---|---|---|
| **Python 3.11+** | — | Tipagem moderna (`X \| Y`, `list[str]`), match/case, performance melhorada |
| **Pydantic v2** | `>=2.6` | Validação de schema (artigo do LLM), modelos imutáveis (`frozen=True`), serialização JSON |
| **pydantic-settings** | `>=2.2` | Carregamento de `.env` + env vars com validação fail-fast |
| **httpx** | `>=0.27` | Cliente HTTP moderno com timeout nativo, suporte HTTP/2, autenticação Basic/Bearer |
| **tenacity** | `>=8.2` | Retry com backoff exponencial para chamadas externas (Jira, Gemini, Confluence) |
| **python-docx** | `>=1.1` | Geração de `.docx` (Word/Google Docs) — workaround pra revisão do time antes da liberação do Confluence |
| **pytest** | `>=8.0` | Framework de testes padrão (**296 testes** na V1.1) |
| **beautifulsoup4** | `>=4.12` | Parser HTML pro scraper GitBook (issue #2) |
| **respx** | `>=0.21` | Mock httpx em testes (issues #2, #10) — dev only |

### Por que NÃO usar

| Não usado | Por que |
|---|---|
| Django/Flask | KIRO é CLI/batch, não web app |
| LangChain | Acopla demais a um provedor, esconde o prompt, dificulta o controle de schema. Preferimos chamar Gemini direto via httpx |
| SQLAlchemy | Não precisamos de banco — output é arquivo |
| scikit-learn | Clustering heurístico simples basta hoje. Quando precisar de embeddings, troca a estratégia plugável |
| Rich/Textual | Spinner ASCII puro (com ANSI colors) suficiente, sem dependência extra |

---

## 7. Pipeline em detalhes

### Estágio 1: Fetch (Jira)

**Arquivo:** `kiro/infrastructure/jira_client.py`

- Endpoint: `GET https://kobesoftware.atlassian.net/rest/api/3/search/jql`
  - *(O endpoint clássico `/rest/api/3/search` foi descontinuado pela Atlassian em 2025. KIRO usa o substituto `/search/jql` com paginação por `nextPageToken`.)*
- Autenticação: **Basic Auth** com email + classic API token (formato `ATATT3xFf...`)
- JQL construído: `project = "{PROJECT_KEY}" AND status in ({STATUSES}) AND updated >= "{SINCE}" ORDER BY updated DESC`
- Campos retornados: `summary`, `description` (ADF), `labels`, `components`, `status`, `resolutiondate`
- Paginação: loop com `nextPageToken` até resposta sem token
- Retry: 3 tentativas com backoff 2-8s para erros HTTP transientes
- Normalização do ADF: percorre recursivamente, extrai apenas nós `type: "text"`, ignora `mentions`, `media`, `emoji`, etc.

### Estágio 2: Cluster

**Arquivo:** `kiro/application/clustering/heuristic.py`

A estratégia heurística faz:

1. **Tokenização** — Cada `summary + description` vira lista de tokens (regex `[a-záéíóúãõâêîôûàèìòùç]{3,}` + filtro de stop-words PT/EN)
2. **TF-DF (Document Frequency)** — Conta em quantos tickets cada termo aparece
3. **Filtro de raridade** — Em corpora ≥ 20 tickets, ignora termos que aparecem em > 70% dos tickets (são ruído)
4. **Extração de bigramas** — Para cada ticket, pega top 15 termos úteis + todos os bigramas onde pelo menos um termo é útil
5. **Clustering por overlap** — Para cada ticket "âncora", agrupa tickets que compartilham ≥ 3 termos com a âncora. Tickets já agrupados são pulados (greedy)
6. **Critério mínimo** — Cluster só sobrevive se tiver ≥ `CLUSTER_MIN_SIZE` (default 3) tickets
7. **Tópico do cluster** — `summary` mais curto do grupo (geralmente o mais "essencial")
8. **Ordenação e top-N** — Clusters ordenados por `count` desc, retorna top `CLUSTER_TOP_N` (default 5)

### Estágio 3: Generate (LLM)

**Arquivo:** `kiro/application/generation/gemini_provider.py`

- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent`
- Autenticação: header `x-goog-api-key: AIzaSy...`
- `generationConfig`:
  - `temperature`: 0.3 (consistente, factual)
  - `maxOutputTokens`: 4000 (cabe um artigo completo + FAQ + tags)
  - `responseMimeType`: `application/json` (força JSON estruturado — Gemini garante)
- **Prompt estruturado** com:
  - Tópico do cluster
  - 5 summaries de exemplo (títulos dos tickets)
  - **Descrições completas** dos 3 tickets com mais conteúdo narrativo (até 500 chars cada, key prefixado: `[OPE-XXX] ...`). Esse bloco transformou drásticamente a qualidade dos artigos — sem ele o LLM trabalhava com 5 frases curtas; com ele ganha ~1500 chars de matéria-prima real
  - Labels e components agregados
  - **Diretrizes obrigatórias** em 7 pontos: ser específico, citar mensagens de erro, distinguir iOS/Android, não inventar causa (usar "Causa a investigar" + hipóteses), FAQ com perguntas reais dos tickets, passos da solução acionáveis (verbo no imperativo + caminhos), tom de varejista
  - Contexto Kobe explícito ("empresa que desenvolve aplicativos móveis para grandes varejistas brasileiros — Amaro, Mr. Cat, Zaffari, Epharma")
  - Schema JSON literal exigido na resposta
- **Validação Pydantic** (`ArticleDraft`) — title/problem/cause/solution obrigatórios, faq e tags opcionais
- **Retry/throttle**:
  - `LLM_REQUEST_DELAY_SECONDS=5` entre chamadas sequenciais (respeita rate limit free tier 15 RPM)
  - 5 tentativas com backoff exponencial 2-30s em 408/429/5xx
  - 4xx (auth, malformed) NÃO é retentável → falha rápido
- **Tratamento de bloqueios do Gemini**:
  - `finishReason=SAFETY|RECITATION|PROHIBITED_CONTENT|BLOCKLIST` → `LLMResponseError` específico
  - `promptFeedback.blockReason` (prompt bloqueado antes da geração) → `LLMResponseError`
- **Continue on cluster failure** — se 1 cluster falha, registra em `errors.json` mas processa os outros

### Estágio 4: Persist (sempre)

**Arquivo:** `kiro/infrastructure/persistence.py`

- `clear_drafts()` — Limpa `output/drafts/*.md` **e** `output/docs/*.docx` no início de cada `--stage generate` (evita acumular de runs antigos)
- `save_tickets()` → `output/tickets.json`
- `save_clusters()` → `output/clusters.json`
- `save_articles()` → `output/articles.json`
- `save_article_markdown()` → `output/drafts/{ticket-key}_{slug-do-titulo}.md`
  - Slugify: lowercase + apenas alfanumérico/underscore, max 60 chars
  - Conteúdo: título + tickets de origem + problema + causa + solução + FAQ + metadados + slogan
  - Strip de numeração duplicada (LLM costuma numerar `"1. fazer X"`, persistência já adiciona `"1. "` → corrige)
- `save_article_docx()` → `output/docs/{ticket-key}_{slug-do-titulo}.docx`
  - Mesmo nome-base do `.md` correspondente
  - Formatação nativa Word: Title, Heading 1, List Number, runs com bold/italic
  - Compatível com Microsoft Word, Pages e Google Docs (sem conversão necessária)
- `save_errors()` → `output/errors.json`
- `save_report()` → `output/report.md` com resumo por etapa + lista de artigos gerados

### Estágio 5: Publish (opcional — Confluence)

**Arquivo:** `kiro/infrastructure/confluence_client.py`

- Endpoint: `POST https://kobesoftware.atlassian.net/wiki/rest/api/content`
- Payload:
  ```json
  {
    "type": "page",
    "status": "draft",
    "title": "[2026-06] Erro de Deeplink em Mr.cat",
    "space": {"key": "AAC"},
    "body": {"storage": {"value": "<html...>", "representation": "storage"}},
    "ancestors": [{"id": "<parent_id_opcional>"}]
  }
  ```
- Conversão Markdown → Confluence Storage Format:
  - Banner de aviso ("Rascunho automático") via `ac:structured-macro name=info`
  - Seções H2 (Problema, Causa raiz, Solução, FAQ, Metadados)
  - Solução como `<ol><li>...</li></ol>` numerada
  - FAQ como `<table>`
  - **Escape HTML** de tudo que vem do LLM (`& → &amp;`, `< → &lt;`, `> → &gt;`) — previne quebra de XML
- Retry: 3 tentativas com backoff
- Se Confluence falha (rede, permissão, 5xx), draft local sobrevive em `output/drafts/`

### Estágio 6: Notify (opcional — Slack)

**Arquivo:** `kiro/infrastructure/slack_client.py`

- POST simples para webhook URL configurado
- Mensagem formatada:
  ```
  *KIRO — análise de tickets concluída*
  Clusters: *5*  |  sucesso: *5*  |  falhas: *0*

  Tópicos processados:
  :large_green_circle: *1. Erro de Deeplink em Mr.cat* — 55 tickets — `https://...`
  :large_green_circle: *2. PBM - Epharma* — 50 tickets — `https://...`
  ...
  ```
- Retry: 3 tentativas

---

## 8. Provedores de LLM

KIRO suporta **3 provedores plugáveis** via `LLM_PROVIDER`. Trocar é só mudar uma linha do `.env`.

### Google Gemini (default)

```dotenv
LLM_PROVIDER=gemini
LLM_API_KEY=AIzaSy...               # https://aistudio.google.com/apikey
LLM_MODEL=gemini-2.5-flash-lite     # mais barato e rápido
LLM_BASE_URL=                        # vazio = default https://generativelanguage.googleapis.com/v1beta
```

**Modelos disponíveis:**

| Modelo | Free tier RPM | Qualidade | Latência | Recomendado para |
|---|---|---|---|---|
| `gemini-2.5-pro` | 5 | ⭐⭐⭐⭐⭐ | Mais lento | Análises críticas |
| `gemini-2.5-flash` | 10 | ⭐⭐⭐⭐ | Rápido | Default geral |
| **`gemini-2.5-flash-lite`** | **15** | ⭐⭐⭐ | Muito rápido | **Default atual — equilíbrio custo/qualidade** |
| `gemini-2.0-flash` | 15 | ⭐⭐⭐⭐ | Rápido | Geração estável anterior |

### Anthropic Claude (alternativa)

```dotenv
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-20250514
LLM_BASE_URL=                       # vazio = default https://api.anthropic.com/v1
```

### Mock (dry-run)

Ativado automaticamente quando `--dry-run` ou `DRY_RUN=true`:
- Não chama API real (custo zero, sem rate limit)
- Drafts gerados com prefixo `[DRY-RUN]` no título
- Conteúdo template baseado nos dados do cluster (tickets, labels, componentes)
- Útil para: gravar demo, testes em CI, validar pipeline sem quota

### Trocando entre provedores

Não precisa tocar em código. Só mudar `.env`:

```bash
# Hoje rodando com Gemini
LLM_PROVIDER=gemini

# Amanhã quer testar Claude?
LLM_PROVIDER=anthropic
```

O domínio (`ArticleDraft`) e o pipeline não mudam.

### Adicionando novo provedor

1. Criar `kiro/application/generation/<provider>_provider.py` implementando interface `LLMProvider`
2. Adicionar caso na `build_llm_provider()` em `factory.py`
3. Adicionar `"<provider>"` no `Literal` de `Settings.llm_provider`
4. Pronto. Nenhuma outra camada muda.

---

## 9. CLI

### Comandos

| Comando | O que faz |
|---|---|
| `kiro run` | Executa pipeline completo (prompt interativo de estilo) |
| `kiro run --style artigo` | Pula prompt, gera Artigo (texto corrido Sobre/Quando/Como) |
| `kiro run --style faq` | Pula prompt, gera FAQ self-service (perguntas/respostas) |
| `kiro run --dry-run` | Roda com mock LLM, sem chamar Gemini real |
| `kiro run --stage fetch` | Só baixa tickets do Jira |
| `kiro run --stage cluster` | Fetch + clusterização |
| `kiro run --stage generate` | Fetch + cluster + geração via LLM |
| `kiro run --stage publish` | Tudo acima + publicação no Confluence (se habilitado) |
| `kiro run --stage notify` | Tudo + notificação Slack (se habilitado) |
| `kiro run --publish-confluence` | Força publicação no Confluence (ignora flag do `.env`) |
| `kiro run --notify-slack` | Força notificação no Slack |
| `kiro run --output-dir custom/` | Muda diretório de saída |
| `kiro run --verbose` | Mostra logs INFO em vez do spinner amigável |
| `kiro fetch-gitbook --public` | **V1.1** Baixa a GitBook pública e gera o cache pro RAG (issue #3) |
| `kiro fetch-confluence-kb` | **V1.1** Baixa o space SUP do Confluence e gera o cache pro style ref (issue #10) |
| `kiro fetch-confluence-kb --space DOCS` | Override do space key (default `CONFLUENCE_KB_SPACE_KEY`) |
| `kiro config-check` | Valida configuração e encerra (sem chamar API) |

### Modos visuais

| Modo | Quando usar | Visual |
|---|---|---|
| **Default (narrator)** | Demo, apresentação, uso normal | Banner ASCII + spinner animado + cores ANSI + slogan |
| **`--verbose`** | Debug, desenvolvimento | Logs INFO completos (timestamp, módulo, mensagem) |

### Exemplos de uso

```bash
# Demo local sem chamar nada externo (perfeito pra vídeo)
kiro run --dry-run

# Rodar pipeline mensal completo
kiro run --publish-confluence --notify-slack

# Só verificar quais tickets vieram
kiro run --stage fetch
cat output/tickets.json

# Validar configuração depois de mudar .env
kiro config-check

# Debug — ver tudo que tá acontecendo
kiro run --verbose
```

---

## 10. Configuração

**Todas as ~40 variáveis** são lidas de `.env` ou variáveis de ambiente. Nada hardcoded. Todas as **flags V1.1 têm default OFF** — `.env` legado da V1.0 continua funcionando sem mudanças.

### Jira (obrigatório)

| Variável | Default | Descrição |
|---|---|---|
| `JIRA_BASE_URL` | — | URL Atlassian (ex: `https://kobesoftware.atlassian.net`) |
| `JIRA_USER_EMAIL` | — | Email da conta autenticada |
| `JIRA_API_TOKEN` | — | **Classic API token** (prefixo `ATATT3x...`), gerado em https://id.atlassian.com/manage-profile/security/api-tokens |
| `JIRA_PROJECT_KEY` | — | Chave do projeto (ex: `OPE`, `CX`, `DAD`) |
| `JIRA_EXTRA_JQL` | `None` | JQL extra opcional (ex: `labels = "customer-impact"`) |
| `JIRA_CLOSED_STATUSES` | `["Done","Closed","Resolved"]` | Lista de statuses considerados "fechado" |
| `JIRA_PAGE_SIZE` | `100` | Tamanho da página de paginação (max 100) |
| `JIRA_TIMEOUT_SECONDS` | `30` | Timeout HTTP |

### Confluence (opcional)

| Variável | Default | Descrição |
|---|---|---|
| `CONFLUENCE_BASE_URL` | `None` | URL Confluence (ex: `https://kobesoftware.atlassian.net/wiki`) |
| `CONFLUENCE_SPACE_KEY` | `None` | Space onde criar drafts (ex: `AAC`) |
| `CONFLUENCE_PARENT_ID` | `None` | ID da página pai (opcional) |
| `CONFLUENCE_TIMEOUT_SECONDS` | `30` | Timeout HTTP |

### Slack (opcional)

| Variável | Default | Descrição |
|---|---|---|
| `SLACK_WEBHOOK_URL` | `None` | Incoming webhook URL |
| `SLACK_TIMEOUT_SECONDS` | `15` | Timeout HTTP |

### LLM

| Variável | Default | Descrição |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` ou `anthropic` |
| `LLM_API_KEY` | — | Chave do provedor |
| `LLM_MODEL` | (depende do provedor) | Ex: `gemini-2.5-flash-lite`, `claude-sonnet-4-20250514` |
| `LLM_BASE_URL` | (depende do provedor) | URL raiz da API. Vazio = default do provedor |
| `LLM_MAX_TOKENS` | `1500` (recomendo `4000`) | Tokens máximos na resposta. **4000 é seguro para artigo completo** |
| `LLM_TEMPERATURE` | `0.3` | Criatividade. Baixo = mais consistente |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout HTTP |
| `LLM_REQUEST_DELAY_SECONDS` | `0.0` (recomendo `5`) | Throttle entre chamadas. Free tier Gemini = 5s |

### Clustering

| Variável | Default | Descrição |
|---|---|---|
| `CLUSTER_STRATEGY` | `heuristic` | Estratégia (só `heuristic` implementado) |
| `CLUSTER_MIN_SIZE` | `3` | Mínimo de tickets para virar cluster |
| `CLUSTER_TOP_N` | `5` | Top N clusters processados por rodada |
| `CLUSTER_OVERLAP_THRESHOLD` | `3` | Termos compartilhados para juntar dois tickets |
| `CLUSTER_TEXT_MAX_LENGTH` | `600` | Tamanho máximo do texto considerado por ticket |

### GitBook RAG (V1.1 — issue #3)

| Variável | Default | Descrição |
|---|---|---|
| `GITBOOK_PUBLIC_URL` | `https://kobeapps.gitbook.io/kobe.io-documentacao` | URL raiz do GitBook (sitemap lido a partir daqui) |
| `GITBOOK_CACHE_PATH` | `kiro/data/gitbook_public_cache.json` | Onde salvar o cache JSON |
| `GITBOOK_REQUEST_DELAY_SECONDS` | `0.5` | Pausa entre páginas no scraper |
| `ENABLE_GITBOOK_RAG` | `false` | Liga o RAG: pipeline carrega cache + injeta chunks no prompt |
| `GITBOOK_RAG_TOP_K` | `3` | Quantos chunks injetar por cluster (max 20) |
| `GITBOOK_RAG_MIN_SCORE` | `0.1` | Cosine-similarity mínimo pra chunk entrar no contexto |

### Confluence SUP — style reference + dedupe (V1.1 — issue #10)

| Variável | Default | Descrição |
|---|---|---|
| `CONFLUENCE_KB_SPACE_KEY` | `SUP` | Space pra ler como style reference |
| `CONFLUENCE_KB_CACHE_PATH` | `kiro/data/confluence_sup_cache.json` | Onde salvar o cache JSON |
| `CONFLUENCE_KB_REQUEST_DELAY_SECONDS` | `0.5` | Pausa entre lotes no scraper |
| `CONFLUENCE_KB_PAGE_SIZE` | `25` | Páginas por request (1..100) |
| `ENABLE_CONFLUENCE_FEW_SHOT` | `false` | Liga few-shot + dedupe |
| `CONFLUENCE_FEW_SHOT_TOP_K` | `2` | Quantos artigos similares mostrar (1..5) |
| `CONFLUENCE_DEDUPE_THRESHOLD` | `0.6` | Cosine pra reportar match de dedupe (0.0..1.0) |

### Output linter (V1.1 — issue #12)

| Variável | Default | Descrição |
|---|---|---|
| `ENABLE_OUTPUT_LINTER` | `false` | Liga o linter (recomendado em prod) |
| `LINTER_BLOCK_MODE` | `skip` | `skip` pula cluster bloqueado, `fail` derruba rodada, `warn` salva mesmo assim |

### Pipeline

| Variável | Default | Descrição |
|---|---|---|
| `LOOKBACK_DAYS` | `30` | Janela retroativa de busca |
| `ENABLE_CONFLUENCE_PUBLISH` | `false` | Publicar no Confluence automaticamente |
| `ENABLE_SLACK_NOTIFY` | `false` | Notificar Slack automaticamente |
| `OUTPUT_DIR` | `output` | Pasta dos artefatos |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DRY_RUN` | `false` | Pular Confluence/Slack + usar Mock LLM |

### Validação fail-fast

Na inicialização, `Settings` valida:
- Campos obrigatórios presentes → senão `ValidationError`
- Tipos corretos (URL é string, números são int/float)
- `ENABLE_CONFLUENCE_PUBLISH=true` exige `CONFLUENCE_BASE_URL` + `CONFLUENCE_SPACE_KEY`
- `ENABLE_SLACK_NOTIFY=true` exige `SLACK_WEBHOOK_URL`
- `DRY_RUN=true` automaticamente desliga Confluence/Slack
- `LLM_MODEL` e `LLM_BASE_URL` vazios → validator aplica defaults baseados no provedor escolhido

Se algo tá errado, KIRO **aborta na inicialização** com mensagem clara, antes de gastar qualquer chamada externa.

---

## 11. Artefatos de saída

A cada rodada, `output/` contém:

```
output/
├── tickets.json        # Lista completa dos tickets coletados (auditoria)
├── clusters.json       # Clusters detectados (com tickets, summaries, labels, components)
├── articles.json       # Artigos gerados (cluster + ArticleDraft pareados)
├── drafts/             # Cada artigo como Markdown legível (revisão local / git)
│   ├── OPE-10305_erro_de_exceção_deeplink_em_aplicativos__mr_cat.md
│   ├── OPE-11226_otimização_da_exibição_de_serviços_na_plataforma_epharma.md
│   ├── OPE-10072_otimização_de_performance_e_fluxos_em_aplicações_de_e-commerce.md
│   └── ...
├── docs/               # Mesmos artigos em .docx (compartilhamento com time / Drive)
│   ├── OPE-10305_erro_de_exceção_deeplink_em_aplicativos__mr_cat.docx
│   ├── OPE-11226_otimização_da_exibição_de_serviços_na_plataforma_epharma.docx
│   ├── OPE-10072_otimização_de_performance_e_fluxos_em_aplicações_de_e-commerce.docx
│   └── ...
├── errors.json         # Falhas registradas por etapa (vazio se tudo OK)
└── report.md           # Relatório executivo da rodada
```

### Estrutura do `report.md`

```markdown
# KIRO — Relatório de execução

- Início:  `2026-06-10T11:44:00.123+00:00`
- Fim:     `2026-06-10T11:44:25.987+00:00`
- Duração: `25.9s`

## Resumo por etapa

- Tickets coletados:    **849**
- Clusters detectados:  **5**
- Artigos gerados (IA): **5**
- Publicados externamente: **0**
- Falhas de publicação: **0**

## Artigos gerados pela IA

1. **Erro de Deeplink em Mr.cat** — 55 tickets
   - tags: deeplink, exceção, Mr.cat, erro, aplicativo
   - tickets de origem: `OPE-10305`, `OPE-10548`, `OPE-9566`, `OPE-9895`, `OPE-9111` …
2. **Otimização da Exibição de Serviços na Plataforma Epharma** — 50 tickets
   - ...

---

_KIRO 1.1.0  ·  your mobile way of presence  —  kobe_
```

### Exportação `.docx` (Word / Google Docs)

Enquanto a permissão de `Create Page` no Confluence não é liberada, o KIRO exporta cada artigo também como **`.docx`** em `output/docs/`. O arquivo abre nativamente em Microsoft Word, Apple Pages e Google Docs — sem conversão necessária.

**Por que existe**: durante a fase de validação interna, o time de doc precisa revisar os rascunhos antes do Confluence. `.docx` permite mandar pelo Drive/Slack/email e receber feedback via comentários no próprio doc.

**Formatação do `.docx`**:

| Elemento | Estilo Word |
|---|---|
| Título do artigo | `Title` (32pt bold) |
| Subtítulo "Rascunho gerado a partir de N tickets..." | itálico cinza |
| Tickets de origem | parágrafo com prefixo bold |
| Problema / Causa raiz / Solução / FAQ / Metadados | `Heading 1` |
| Passos da solução | `List Number` (renumera nativamente se editado) |
| Pergunta da FAQ | bold; resposta logo abaixo em texto normal |
| Rodapé com slogan | centralizado, itálico, 9pt cinza |

**Workflow recomendado — upload em massa no Drive**:

```bash
open output/docs/                     # abre o Finder na pasta
```

1. `⌘+A` no Finder → seleciona os 5 (ou N) `.docx`
2. Arrasta tudo pra uma pasta nova no `drive.google.com`
3. Clica direito em cada → **"Abrir com Google Docs"** → converte mantendo formatação
4. Compartilha a pasta com o time de doc, permissão **"Comentário"**
5. Time revisa direto no Google Docs com comentários colaborativos

**Tamanho típico**: ~37 KB por arquivo. 5 artigos = ~185 KB total. Trivial pra anexar/subir.

**Atualização entre rodadas**: cada `kiro run --stage generate` chama `clear_drafts()` que apaga `output/drafts/*.md` **e** `output/docs/*.docx` antes de gerar os novos. Sem acúmulo de versões.

### Estrutura de cada `draft/*.md`

```markdown
# Erro de Deeplink em Mr.cat

> Rascunho gerado a partir de 55 tickets.

**Tickets de origem:** `OPE-10305`, `OPE-10548`, `OPE-9566`, ...

## Problema

Usuários e sistemas externos estão enfrentando dificuldades para serem
direcionados corretamente para conteúdos específicos dentro do aplicativo
através de links externos (deeplinks)...

## Causa raiz

A causa raiz provável é uma configuração incorreta ou ausente dos esquemas
de URL (URL schemes) ou de Universal Links/App Links no ambiente de produção...

## Solução

1. Verifique a configuração dos URL schemes no `Info.plist` (iOS) e
   `AndroidManifest.xml` (Android).
2. Confirme se os Universal Links (iOS) e App Links (Android) estão
   corretamente configurados...
3. ...

## Perguntas frequentes

**O que é um Deeplink?**

Um deeplink é um tipo especial de link que direciona o usuário para um
conteúdo específico dentro de um aplicativo móvel...

**Como testar um Deeplink?**

Você pode testar enviando-o para si mesmo via mensagem, email ou
ferramentas de teste online...

## Metadados

- Componentes: —
- Labels: jira_escalated, jira_update
- Tags: deeplink, fom, ios, android, url scheme, universal links

---

_KIRO 1.1.0  ·  your mobile way of presence  —  kobe_
```

---

## 12. Segurança

### Princípios

1. **Nenhum segredo hardcoded** — Tokens, URLs, project keys, modelos: tudo via env
2. **Tokens como `SecretStr`** — Pydantic não imprime em `repr()` nem em `str()`
3. **Redação automática de logs** — Filtro regex bloqueia padrões `token=`, `api_key=`, `Bearer X`, `https://hooks.slack.com/*` em qualquer log
4. **Validação de input externo** — Schema Pydantic rejeita resposta malformada do LLM
5. **HTML escape no Confluence** — Tudo que vem do LLM passa por `& → &amp;` antes de virar Storage Format (previne XML injection)
6. **Service account ready** — Email + token podem ser de service account isolado, com permissões mínimas
7. **`.env` no `.gitignore`** — Credenciais nunca vão pro Git por acidente
8. **Fail-fast em config inválida** — Aborta antes de gastar API com configuração quebrada

### Permissões mínimas recomendadas

| Sistema | Permissão necessária |
|---|---|
| Jira | `Browse Projects` no projeto configurado, `View Issues` |
| Confluence | `Create Page`, `Edit Page` no space configurado |
| Gemini | Apenas a chave de API (sem escopos extras) |
| Slack | Incoming webhook do canal de destino |

### Como o KIRO trata credenciais

- Lidas **uma vez** na inicialização via `pydantic-settings`
- Guardadas como `SecretStr` em memória
- Passadas para clientes HTTP via parâmetros de função (nunca em log)
- Filtro de logging substitui qualquer padrão suspeito por `[REDACTED]`

---

## 13. Resiliência

### Retries por componente

| Componente | Tentativas | Backoff | Triggers |
|---|---|---|---|
| **Jira** | 3 | 2-8s exponencial | `httpx.HTTPError`, `TimeoutException` |
| **Gemini** | 5 | 2-30s exponencial | 408, 429, 5xx (4xx não-retentáveis) |
| **Anthropic** | 5 | 2-30s exponencial | Mesma lógica do Gemini |
| **Confluence** | 3 | 2-8s exponencial | `httpx.HTTPError` |
| **Slack** | 3 | 1-5s exponencial | `httpx.HTTPError` |

### Throttling

- `LLM_REQUEST_DELAY_SECONDS` (default 0, recomendo 5) — pausa entre chamadas sequenciais LLM
- Em **dry-run o throttle é pulado** (mock não chama API → não precisa esperar)
- Throttle só aplicado entre clusters, não entre retries (retries têm seu próprio backoff via tenacity)

### Continue on failure

Se 1 cluster falha na geração:
- Erro registrado em `output/errors.json`
- Pipeline **continua para os próximos clusters**
- Drafts dos clusters que passaram são salvos normalmente
- Exit code = 1 ao final (sinaliza falha parcial)

Se Confluence falha na publicação:
- Erro registrado, draft local sobrevive
- Pipeline tenta publicar os próximos
- Slack notifica com `[FAIL]` marcado pros que falharam

Se Slack falha:
- Erro registrado, mas tudo já foi gerado e publicado
- Exit code = 1

### Trace de erros sem traceback feio

Erros de provedor LLM (após exausto retries) são convertidos para `LLMError`/`LLMResponseError` antes de subir. Isso significa que:
- O pipeline vê uma exceção tipada e amigável
- Sem `httpx.HTTPStatusError: Server error '503'` cheio de traceback no terminal
- Mensagem fica clean: `falhei em 'Documentação' — Gemini API esgotou retries (status 429)`

---

## 14. Testes

### Suite de 296 testes (V1.1)

```
tests/
├── test_adf.py                    # parser ADF flatten (V1.0)
├── test_adf_to_markdown.py        # parser ADF→md preservando estrutura (V1.1 #10)
├── test_anthropic_parser.py       # parse JSON Anthropic
├── test_cli.py                    # smoke do CLI (fetch-gitbook, fetch-confluence-kb)
├── test_clustering.py             # heurística TF-DF + bigramas
├── test_confluence_kb_loader.py   # scraper SUP + paginação + filtro meta (V1.1 #10)
├── test_customer_faq.py           # geração e parse FAQ B2B
├── test_gemini_parser.py          # parse + extract_text + safety blocks
├── test_gitbook_loader.py         # scraper GitBook público (V1.1 #2)
├── test_kb_context.py             # helper bloco "REFERÊNCIA KOBE" (V1.1 #3)
├── test_lint.py                   # OutputLinter engine + dispatch (V1.1 #12)
├── test_lint_rules.py             # 10 regras BLOCK/WARN individuais (V1.1 #12)
├── test_normalization.py          # tokenize, stop-words, accents
├── test_persistence.py            # save tickets/clusters/md/docx
├── test_pipeline_lint.py          # pipeline + linter skip/fail/warn (V1.1 #12)
├── test_pipeline_rag.py           # pipeline + retriever GitBook (V1.1 #3)
├── test_pipeline_style.py         # pipeline + style_finder + dedupe (V1.1 #10)
├── test_provider_factory.py       # gemini/anthropic/mock selection
├── test_retrieval.py              # KnowledgeRetriever TF-IDF (V1.1 #3)
├── test_settings.py               # validators + secrets + flags V1.1
├── test_style_examples.py         # helper bloco "EXEMPLOS DO ESTILO KOBE" (V1.1 #10)
└── test_style_reference.py        # StyleReferenceFinder + dedupe (V1.1 #10)
```

**Crescimento por release:**
- V1.0: 46 testes
- V1.0.1: 57 testes (estilo FAQ B2B)
- V1.1 issue #2: 99 testes (+GitBook scraper)
- V1.1 issue #3: 119 testes (+RAG)
- V1.1 issue #10: 227 testes (+Confluence SUP)
- V1.1 issue #12: **296 testes** (+linter)

### Como rodar

```bash
# Suite completa
.venv/bin/python -m pytest

# Ou com pytest instalado no venv (que está)
pytest

# Verboso
pytest -v

# Só testes de clustering
pytest tests/test_clustering.py
```

### O que **não está coberto** por testes unitários

- Integração real com Jira/Gemini/Confluence (precisaria mock de HTTP ou ambiente de teste)
- Renderização visual do spinner (depende de TTY)
- Comportamento do agendamento cron (testado manualmente)

---

## 15. Setup e operação

### Instalação local (primeira vez)

```bash
# 1. Clonar o repositório
cd ~/path/to/parent
git clone <repo-url> kiro
cd kiro

# 2. Criar venv
python3 -m venv .venv

# 3. Ativar venv
source .venv/bin/activate

# 4. Instalar dependências
pip install -r requirements.txt

# 5. Instalar o pacote como editable (registra o comando `kiro`)
pip install -e .

# 6. Configurar credenciais
cp .env.example .env
# Editar .env com seus valores reais
```

### Uso recorrente

```bash
# Toda vez que abrir terminal novo:
cd "/path/to/kiro"
source .venv/bin/activate

# Rodar
kiro run                    # ciclo completo
kiro run --dry-run          # demo sem custo
kiro config-check           # valida settings
```

### Comando `kiro` global (sem precisar ativar venv)

Adicionar ao `~/.zshrc`:

```bash
# KIRO automation
kiro() {
    "/Users/matheussilva/Documents/Developer2026/Automação Kobe/.venv/bin/kiro" "$@"
}
```

Recarregar:
```bash
source ~/.zshrc
```

Agora `kiro run` funciona de **qualquer pasta**, sem precisar ativar nada.

### Agendamento mensal via GitHub Actions

Arquivo: `.github/workflows/monthly.yml`

Roda automaticamente **dia 1 do mês às 11:00 UTC (08:00 BRT)**:

```yaml
on:
  schedule:
    - cron: "0 11 1 * *"
```

Secrets necessários (`Settings → Secrets and variables → Actions`):
- `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`
- `LLM_API_KEY`
- `CONFLUENCE_BASE_URL`, `CONFLUENCE_SPACE_KEY`, `CONFLUENCE_PARENT_ID` (se for publicar)
- `SLACK_WEBHOOK_URL` (se for notificar)

Outputs ficam disponíveis como artifact downloadable na aba Actions.

### Monitoramento

- Cada rodada gera `output/report.md` com resumo
- `output/errors.json` lista falhas
- Exit code 0 = sucesso total, 1 = falha parcial, 2 = config inválida
- Em GitHub Actions, jobs vermelhos sinalizam problema → email automático

---

## 16. Métricas observadas

Coleta real em **2026-06-10** sobre o projeto **OPE**:

| Métrica | Valor |
|---|---|
| Tickets fechados nos últimos 30 dias | **849** |
| Tempo total de fetch (8 páginas) | ~5 segundos |
| Clusters detectados (≥3 tickets) | **54** |
| Top 5 selecionados para gerar artigos | 5 |
| Tickets cobertos pelos top 5 | **220** (26% do total) |
| Tempo total de pipeline completo | ~25-30 segundos |
| Falhas de geração no Gemini free tier | 0-1 por rodada (transientes) |

### Top 5 clusters detectados (2026-06-10)

| # | Tópico | Tickets | Tags geradas pelo Gemini |
|---|---|---|---|
| 1 | Erro de Deeplink em Mr.cat | 55 | deeplink, ios, android, url scheme, universal links |
| 2 | Otimização da Exibição de Serviços na Epharma | 50 | PBM, Epharma, CMS, Backend |
| 3 | Análise de Performance | 35 | performance, otimização, fluxo |
| 4 | Documentação | 35 | documentação |
| 5 | QA: Execução dos testes | 29 | qa, testes |

### Qualidade dos artigos

Cada draft gerado pelo Gemini contém:
- Título descritivo
- Descrição do problema do ponto de vista do cliente (2-3 frases)
- Análise de causa raiz provável (1-2 frases)
- **Passo a passo numerado de solução** (3-8 passos)
- **FAQ** com 2-3 perguntas relevantes
- 5-8 tags

Tamanho médio: ~2.5 KB de Markdown por artigo.

---

## 17. Roadmap

### v1.0 (entregue 2026-06-10)

- [x] Pipeline completo Jira → Cluster → Gemini → Markdown local
- [x] CLI com 5 stages + dry-run + verbose
- [x] Suporte a Gemini + Anthropic + Mock
- [x] 46 testes
- [x] Visual com spinner animado + branding Kobe
- [x] Cleanup automático de drafts entre rodadas
- [x] Throttle e retry inteligentes
- [x] **Exportação `.docx`** (Word/Google Docs compatível) — workaround pra revisão do time antes da liberação do Confluence
- [x] **Cluster enriquecido com descrições** — `Cluster.sample_descriptions` carrega excertos de 500 chars dos 3 tickets com mais conteúdo
- [x] **Prompt cirúrgico** — instruções específicas anti-genéricas, contexto Kobe (varejistas brasileiros)

### v1.0.1 (entregue 2026-06-10)

- [x] **Dois estilos de output por rodada** — `--style artigo` (Sobre/Quando/Como/FAQ) ou `--style faq` (perguntas/respostas self-service B2B)
- [x] **Tom externo cuidadoso** — headers customer-facing, códigos OPE-XXX isolados em "nota de revisão" fora do corpo
- [x] **Prompt 100% externo** — proibições absolutas (não vazar root cause, bug, workaround, código)

### v1.1 (entregue 2026-06-12)

- [x] **RAG com GitBook público da Kobe** (issue #3 / PR #9) — scraper + TF-IDF + injeção no prompt
- [x] **GitBook scraper público** (issue #2 / PR #8) — 1146 chunks de 206 páginas, sitemap index suportado
- [x] **Confluence SUP como style reference** (issue #10 / PR #11) — 1554 chunks de 324 artigos, few-shot pro tom + dedupe contra existentes
- [x] **Output linter** (issue #12 / PR #13) — 10 regras determinísticas, BLOCK + WARN, modo skip/fail/warn
- [x] **ADF→markdown parser** (V1.1) — preserva estrutura (headings, listas, tabelas)
- [x] **296 testes verdes**

### v1.1.x (em aberto no milestone)

- [ ] **GitBook interno autenticado** (issue #4) — extensão do scraper público pra space com auth Token
- [ ] **Atualizar KIRO.md** (issue #5) — este documento (em progresso)
- [ ] Publicação ao vivo no Confluence (aguardando permissão de Create Page no space AAC)
- [ ] Notificação Slack (aguardando decisão sobre canal)
- [ ] GitHub Actions ativado em produção (rodada mensal automática)
- [ ] Métricas de ROI registradas após primeira rodada real

### v1.2 (eixos de qualidade — discutidos em 2026-06-12, não criados ainda)

- [ ] **Eval set + métrica** (eixo D) — 10-20 clusters com "gold standard" escrito pela chefe + pytest que mede similaridade/violação. Permite iterar sem regressão.
- [ ] **Cluster com metadata estruturada** (eixo B) — extrair plataforma (iOS/Android), varejista, componente como hint estruturado pro LLM. Reduz frases genéricas ("no aplicativo" → "no app Amaro iOS").
- [ ] Detecção de duplicatas — busca antes de criar (parcialmente entregue via dedupe SUP)
- [ ] Multi-projeto — rodar em CX e DAD também

### v2.0 (longo prazo)

- [ ] Estratégia de clustering com **embeddings** (em vez de heurística TF-DF) — usar `text-embedding-004` do Gemini ou similar
- [ ] **Atlassian Rovo** como camada de busca/retrieval — "essa dúvida já tem artigo?"
- [ ] Geração de **screenshots/diagramas** quando faz sentido
- [ ] Multi-language — gerar em PT + EN automaticamente
- [ ] Feedback loop — métricas de quais drafts foram efetivamente publicados / editados / descartados
- [ ] **Retry com prompt corretivo** — quando linter bloqueia, reenviar pro LLM com instrução "remova X". Custo extra de tokens, mas evita perder cluster.

---

## 18. Glossário

| Termo | Significado |
|---|---|
| **ADF** | Atlassian Document Format — formato JSON usado pelo Jira/Confluence para representar texto rico (description, comments). KIRO tem parser próprio em `kiro/utils/adf.py` |
| **JQL** | Jira Query Language — linguagem de busca tipo SQL para tickets. Ex: `project = "OPE" AND status = Done` |
| **Storage Format** | Formato XML/HTML usado pelo Confluence Cloud para armazenar conteúdo de páginas. Não é HTML puro — tem macros tipo `<ac:structured-macro>` |
| **Basic Auth (Atlassian)** | Autenticação com email + API token, encodada em Base64 no header `Authorization: Basic ...` |
| **TF-DF** | Term Frequency / Document Frequency — métrica de raridade de termos no corpus. Termo que aparece em poucos tickets é mais informativo |
| **Stop-words** | Palavras de função (de, da, o, the, of) que adicionam ruído ao clustering. KIRO mantém lista PT+EN em `normalization.py` |
| **Bigrama** | Par de palavras consecutivas (ex: "login bloqueado"). Mais discriminativo que palavras isoladas |
| **`finishReason`** | Campo da resposta do Gemini explicando por que parou de gerar (STOP, MAX_TOKENS, SAFETY, ...) |
| **`promptFeedback.blockReason`** | Quando o **prompt** foi bloqueado antes da geração (não confundir com `finishReason`) |
| **Throttle** | Pausa intencional entre chamadas externas pra respeitar rate limit |
| **Backoff exponencial** | Padrão de retry onde cada tentativa espera o dobro da anterior (2s, 4s, 8s, 16s, 30s) |
| **Pydantic `SecretStr`** | Wrapper de string que não imprime o valor em `repr()` ou `str()`. Tem `.get_secret_value()` para acesso explícito |
| **Tenacity** | Biblioteca Python para retry com backoff. Decorator `@retry` no método que pode falhar |
| **`.docx` (Office Open XML)** | Formato de documento Word desde 2007. É um ZIP com XMLs dentro. Abre nativamente em Word, Pages e Google Docs |
| **python-docx** | Biblioteca Python que gera `.docx` programaticamente. Suporta estilos nativos (Heading 1, Title, List Number) |

---

## 19. Troubleshooting

### `zsh: command not found: python`

Você esqueceu de ativar o venv. Rode `source .venv/bin/activate`. Seu prompt deve passar a começar com `(.venv)`.

Alternativa sem ativar: use `.venv/bin/python -m kiro ...` ou `.venv/bin/kiro ...`.

### `command not found: kiro`

Mesmo problema. Ative o venv ou use o caminho completo, ou configure a shell function em `~/.zshrc` (ver seção [15](#15-setup-e-operação)).

### `ModuleNotFoundError: No module named 'pydantic'`

Venv não ativado. Mesma solução acima.

### `[KIRO] configuração inválida: ENABLE_CONFLUENCE_PUBLISH=true exige ...`

Você habilitou Confluence sem preencher `CONFLUENCE_BASE_URL` e `CONFLUENCE_SPACE_KEY`. Preencha no `.env` ou desabilite.

### Jira retorna `401 Client must be authenticated`

Token Atlassian é do tipo errado. KIRO usa **Classic API tokens** (prefixo `ATATT3xFf...`). Se o seu começa com `ATCTT3xFf...` é Connect Session Token (não funciona). Gere o tipo correto em https://id.atlassian.com/manage-profile/security/api-tokens clicando em **"Create API token"** (não "with scopes").

### Jira retorna `410 Gone`

O endpoint clássico `/rest/api/3/search` foi removido pela Atlassian. KIRO já usa o novo `/rest/api/3/search/jql`. Se está vendo este erro, está rodando código antigo — atualize.

### Gemini retorna `429 Too Many Requests`

Free tier estourado. Opções:
- Espera (quota reseta diariamente)
- Aumenta `LLM_REQUEST_DELAY_SECONDS`
- Troca pra modelo com free tier maior (`gemini-2.5-flash-lite` tem 15 RPM, `gemini-2.0-flash` tem 15 RPM)
- Habilita billing no Google Cloud (vira pay-per-use, sem rate limit)
- Roda com `--dry-run` (mock, custo zero)

### Gemini retorna `503 Service Unavailable`

Modelo sobrecarregado temporariamente. KIRO retry 5x com backoff até 30s. Se persistir, troca de modelo ou tenta mais tarde.

### `Gemini bloqueou a resposta: finishReason=SAFETY`

Filtros de segurança do Gemini detectaram conteúdo sensível no prompt ou na resposta. Revise os summaries dos tickets do cluster (PII, conteúdo sensível, etc.). Ou troque pro Claude que tem filtros diferentes.

### `resposta Gemini não é JSON válido: Unterminated string`

O LLM começou a gerar JSON mas foi cortado por `LLM_MAX_TOKENS`. Aumenta para `4000` (já é o default recomendado).

### Nenhum cluster gerado

Janela muito curta ou `CLUSTER_MIN_SIZE` muito alto. Opções:
- Aumenta `LOOKBACK_DAYS` para 60 ou 90
- Baixa `CLUSTER_MIN_SIZE` para 2
- Baixa `CLUSTER_OVERLAP_THRESHOLD` para 2

### `x linter pulou '<cluster>' (N violações)` no resumo

**Não é erro, é proteção funcionando.** O `OutputLinter` (V1.1 issue #12) detectou que o LLM gerou conteúdo proibido (códigos OPE-, jargão tipo "bug" / "WebView", URL externa). Em `LINTER_BLOCK_MODE=skip` (default), o cluster é pulado sem salvar — outros clusters continuam normais.

Pra ver detalhes da violação:
```bash
cat output/errors.json
```

Se aparece **sempre** no mesmo cluster, o LLM está consistentemente vazando — vale ajustar o prompt ou revisar o cluster manualmente.

### `kiro fetch-confluence-kb` retorna `401 Unauthorized`

Token Atlassian não tem acesso de leitura ao space SUP. Confirme com a chefe se o seu usuário tem permissão READ. O mesmo token JIRA é usado pra Confluence Cloud.

### Cache GitBook ou SUP ausente — RAG/few-shot não ativa

Mesmo com flag `ENABLE_GITBOOK_RAG=true`, se `kiro/data/gitbook_public_cache.json` não existir, o KIRO loga warning e segue sem RAG. Solução: rode `kiro fetch-gitbook --public` antes da primeira `kiro run`. Mesmo pro SUP: `kiro fetch-confluence-kb`.

### Confluence retorna `400 Bad Request` na criação de página

- Verifique se `CONFLUENCE_SPACE_KEY` existe
- Verifique se sua conta tem **Create Page** no space
- Se passou `CONFLUENCE_PARENT_ID`, verifique se a página existe

### Slack webhook retorna `404`

Webhook foi revogado ou URL está errada. Crie um novo em https://api.slack.com/messaging/webhooks e atualize `SLACK_WEBHOOK_URL`.

---

## 20. Árvore completa do projeto

```
Automação Kobe/
├── .env                          # credenciais (gitignored)
├── .env.example                  # template com todas as 27 variáveis
├── .gitignore                    # ignora .env, output/, .venv/, caches
├── .github/
│   └── workflows/
│       └── monthly.yml           # cron mensal + workflow_dispatch
├── KIRO.md                       # este documento (atualizado V1.1)
├── README.md                     # setup + quickstart
├── task.md                       # critérios da chefe (referência)
├── pyproject.toml                # metadata + entry point `kiro`
├── requirements.txt              # httpx, pydantic, pydantic-settings, tenacity, beautifulsoup4
├── requirements-dev.txt          # + pytest, respx
├── kiro/                         # pacote Python (Clean Architecture)
│   ├── __init__.py               # __version__ = "1.1.0"
│   ├── __main__.py               # entry point `python -m kiro`
│   ├── data/                     # cache JSON dos RAG sources (gitignored)
│   │   ├── .gitkeep
│   │   ├── gitbook_public_cache.json    # V1.1 #2 — 860KB, 1146 chunks
│   │   └── confluence_sup_cache.json    # V1.1 #10 — 1.2MB, 1554 chunks
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py           # Pydantic Settings, validators (~40 vars)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py             # Ticket, Cluster, ArticleDraft, CustomerFAQ, GitBookChunk, ...
│   │   └── exceptions.py         # KiroError, ConfigError, JiraError, LLMError, LinterBlocked
│   ├── application/
│   │   ├── __init__.py
│   │   ├── pipeline.py           # Pipeline orchestrator + dedupe + lint
│   │   ├── normalization.py      # tokenize, normalize_text, STOP_WORDS
│   │   ├── retrieval.py          # V1.1 #3 — KnowledgeRetriever (TF-IDF GitBook)
│   │   ├── style_reference.py    # V1.1 #10 — StyleReferenceFinder + dedupe (SUP)
│   │   ├── lint.py               # V1.1 #12 — OutputLinter engine
│   │   ├── lint_rules.py         # V1.1 #12 — regras BLOCK + WARN
│   │   ├── clustering/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── heuristic.py
│   │   └── generation/
│   │       ├── __init__.py
│   │       ├── base.py           # LLMProvider ABC (com kb_context + style_examples)
│   │       ├── factory.py
│   │       ├── gemini_provider.py
│   │       ├── anthropic_provider.py
│   │       ├── mock_provider.py
│   │       ├── kb_context.py     # V1.1 #3 — helper bloco "REFERÊNCIA KOBE"
│   │       └── style_examples.py # V1.1 #10 — helper bloco "EXEMPLOS DO ESTILO KOBE"
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── jira_client.py
│   │   ├── confluence_client.py
│   │   ├── confluence_kb_loader.py  # V1.1 #10 — SUP scraper
│   │   ├── gitbook_loader.py        # V1.1 #2 — GitBook público scraper
│   │   ├── slack_client.py
│   │   ├── docx_exporter.py
│   │   └── persistence.py
│   ├── interfaces/
│   │   ├── __init__.py
│   │   └── cli.py                # argparse com 4 subcomandos (run, config-check,
│   │                             # fetch-gitbook, fetch-confluence-kb)
│   └── utils/
│       ├── __init__.py
│       ├── adf.py                # extract_text_from_adf (flatten)
│       ├── adf_to_markdown.py    # V1.1 #10 — ADF→markdown preservando estrutura
│       ├── branding.py           # banner, footer (com lint + dedupe info)
│       ├── logging.py            # configure_logging + SecretRedactingFilter
│       └── progress.py           # Narrator (spinner ANSI animado)
├── tests/                        # 296 testes pytest
│   └── ... (ver §14)
└── output/                       # gerado a cada rodada (gitignored)
    ├── tickets.json
    ├── clusters.json
    ├── articles.json
    ├── drafts/                   # Artigo md
    ├── docs/                     # Artigo docx
    ├── faqs_md/                  # V1.0.1 — FAQ md
    ├── faqs_docx/                # V1.0.1 — FAQ docx
    ├── errors.json
    └── report.md
```

---

## Apêndice — referências rápidas

- **Atlassian API tokens:** https://id.atlassian.com/manage-profile/security/api-tokens
- **Gemini API key:** https://aistudio.google.com/apikey
- **Gemini docs:** https://ai.google.dev/gemini-api/docs
- **Slack webhooks:** https://api.slack.com/messaging/webhooks
- **Jira REST API v3:** https://developer.atlassian.com/cloud/jira/platform/rest/v3/
- **Confluence REST API:** https://developer.atlassian.com/cloud/confluence/rest/v1/
- **Cron syntax:** https://crontab.guru

---

_KIRO 1.1.0  ·  your mobile way of presence  —  kobe_
