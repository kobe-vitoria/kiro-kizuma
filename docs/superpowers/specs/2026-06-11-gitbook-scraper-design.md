# GitBook Public Scraper — Design Spec

**Issue**: [#2 feat(rag): scraper + cache local da GitBook pública da Kobe](https://github.com/kobe-matheussilva/KIRO/issues/2)
**Milestone**: V1.1
**Branch**: `feature/gitbook-scraper` (a criar a partir de `main`)
**Estimativa**: ~4h
**Data**: 2026-06-11

## Contexto

KIRO hoje gera artigos só com base em tickets do Jira. Esse PR é o primeiro passo de RAG: baixar e cachear o GitBook público da Kobe (https://kobeapps.gitbook.io/kobe.io-documentacao) para que, na issue #3, o pipeline de geração consiga consultar conteúdo já documentado antes de pedir ao Gemini que invente uma resposta.

Esse PR **não toca o pipeline de geração**. Apenas popula o cache.

## Decisões já tomadas

| # | Decisão | Escolha |
|---|---------|---------|
| 1 | Confluence SUP scraper | Issue #6 separada depois — fora do escopo desse PR |
| 2 | Descoberta de páginas | `sitemap.xml` (sem crawler recursivo, sem seed list) |
| 3 | Estratégia de chunking | Por seção/heading (h1/h2/h3), com sub-divisão se > 1000 chars |
| 4 | Parser | BeautifulSoup4 |
| 5 | HTTP client | `httpx` + `tenacity` (já no projeto) |

Alternativas descartadas: Scrapy (overkill pra dezenas de páginas estáticas), Playwright/Selenium (GitBook serve HTML estático), API não-documentada do GitBook (frágil).

## Arquitetura

Módulo único de infrastructure. Sem mudanças em domain/application/generation/persistence.

```
kiro/infrastructure/gitbook_loader.py    # core: fetch + parse + chunk + persist
kiro/interfaces/cli.py                   # +1 subcomando: fetch-gitbook --public
kiro/config/settings.py                  # +3 settings novos
kiro/data/                               # nova pasta (gitignored)
tests/test_gitbook_loader.py             # mocks via respx
```

## Contrato público

```python
def scrape_public_gitbook(
    base_url: str,
    output_path: Path,
    *,
    narrator: Narrator | None = None,
    request_delay_seconds: float = 0.5,
) -> ScrapingResult: ...

@dataclass(frozen=True)
class ScrapingResult:
    pages_fetched: int
    chunks_written: int
    failed_urls: list[str]
    output_path: Path
```

A função retorna ao invés de levantar para que a CLI consiga apresentar o resumo final mesmo havendo falhas parciais.

## Fluxo de dados

```
sitemap.xml  →  [URL list]  →  for each url:
                                  httpx GET (com retry tenacity)
                                  BS4 parse
                                  extract main content
                                  split em chunks por heading
                              →  [Chunk list]  →  JSON file
```

## Schema do cache JSON

```json
{
  "fetched_at": "2026-06-11T14:32:00Z",
  "source": "gitbook_public",
  "base_url": "https://kobeapps.gitbook.io/kobe.io-documentacao",
  "chunks": [
    {
      "page_title": "Configurando notificações push",
      "page_url": "https://kobeapps.gitbook.io/.../config-push-abc123",
      "section_title": "Pré-requisitos",
      "section_anchor": "pre-requisitos",
      "content": "Antes de começar, certifique-se de que...",
      "char_count": 487
    }
  ]
}
```

Decisões do schema:

- `fetched_at` no topo (não por chunk) — economiza espaço; o cache inteiro é regenerado de uma vez
- `source: "gitbook_public"` deixa explícito para quando a issue #4 (GitBook interno autenticado) adicionar chunks com `source: "gitbook_internal"` no mesmo arquivo ou paralelo
- `section_anchor` ajuda a issue #3 a montar URLs deep-link (`{page_url}#{section_anchor}`)
- `char_count` é redundante (derivável) mas evita recontagem na issue #3

## Descoberta via sitemap

1. `GET {base_url}/sitemap.xml`
2. Parsear XML com `xml.etree.ElementTree` (stdlib — sem dep nova). Extrair todos os `<loc>`
3. Filtrar URLs que começam com `base_url` (defesa contra sitemap apontar para fora)
4. Deduplicar e retornar a lista

Se sitemap responder 404 ou falhar parsing → **raise hard** com mensagem clara: *"GitBook deve expor /sitemap.xml. Verifique GITBOOK_PUBLIC_URL."*

Sem fallback para crawler — sitemap é load-bearing por design.

## Parser e chunking por seção

Para cada página baixada:

1. BS4 acha o container principal de conteúdo. GitBook usa `<main>` ou `[data-testid="page.contentEditor"]` dependendo da versão — tentar ambos, com fallback ao primeiro `<article>` se nenhum bater
2. Iterar children do container em ordem do DOM, mantendo o heading mais recente como "seção corrente"
3. Acumular texto até bater no próximo heading do mesmo nível ou superior (encerra o chunk)
4. **Se a seção exceder 1000 chars**: dividir em sub-chunks de ~800 chars, quebrando preferencialmente em fim de parágrafo (`\n\n`). Cada sub-chunk repete o `section_title`
5. **Se a seção tiver <200 chars**: ainda salva — informação curta pode ser relevante para retrieval (ex.: "Suporte apenas iOS 15+")

`page_title` = primeiro `<h1>` do conteúdo, ou `<title>` do HTML como fallback.
`section_anchor` = `id` do heading se presente, senão slugify do `section_title`.

## Error handling

| Situação | Tratamento |
|----------|------------|
| Sitemap inacessível ou inválido | Raise — operação não tem sentido sem ele |
| Página individual retorna 4xx/5xx final | Registra em `failed_urls`, continua, narrator avisa no fim |
| Página com HTML inesperado (sem container) | Registra em `failed_urls`, continua |
| Erro de parsing de uma página | Registra em `failed_urls`, continua |
| Filesystem (path inválido, sem permissão) | Raise — bug de configuração |

Retries via `tenacity` nos `httpx.get`: backoff 2-30s, max 3 tentativas, retry apenas em 408/429/5xx. Mesmo padrão do resto do projeto.

Throttle entre requests: `request_delay_seconds` (default 0.5s) para ser educado com GitBook.

## CLI

```bash
kiro fetch-gitbook --public
```

Saída esperada:

```
🌐 KIRO · fetch-gitbook --public
⠋ Lendo sitemap... 47 páginas encontradas
⠋ Baixando: Configurando notificações push (12/47)
...
✓ 45 páginas baixadas, 2 falhas
✓ 158 chunks salvos em kiro/data/gitbook_public_cache.json
✓ fetched_at: 2026-06-11T14:32:00Z
```

Em modo `--verbose`, lista cada URL que falhou no final.

## Settings (pydantic-settings)

```python
GITBOOK_PUBLIC_URL: str = "https://kobeapps.gitbook.io/kobe.io-documentacao"
GITBOOK_CACHE_PATH: Path = Path("kiro/data/gitbook_public_cache.json")
GITBOOK_REQUEST_DELAY_SECONDS: float = 0.5
```

Defaults razoáveis. URL é pública — sem segredo. Tudo overridable por `.env`.

`.env.example` recebe as três linhas com comentário explicando.

## .gitignore

Adicionar:

```
kiro/data/*_cache.json
```

A pasta `kiro/data/` em si fica versionada com um `.gitkeep` para que o caminho exista no clone.

## Estratégia de testes

Usar `respx` para mockar `httpx` (compatível com o stack atual). Sem rede em testes.

| # | Teste | Cobre |
|---|-------|-------|
| 1 | `test_sitemap_parsing` | XML mock com 3 URLs → lista correta |
| 2 | `test_sitemap_filters_external_urls` | URLs fora de base_url descartadas |
| 3 | `test_sitemap_404_raises` | Falha hard com mensagem clara |
| 4 | `test_chunk_by_heading` | HTML com h1+h2+h2 → 3 chunks com section_title correto |
| 5 | `test_chunk_split_when_oversized` | Seção >2000 chars → ~3 sub-chunks preservando title |
| 6 | `test_chunk_keeps_short_section` | Seção <200 chars ainda é salva |
| 7 | `test_page_404_continues` | URL 404 → registra em failed_urls e continua |
| 8 | `test_full_pipeline_with_mocks` | Sitemap + 2 páginas → JSON gerado, valida schema completo |
| 9 | `test_fetched_at_is_iso8601_utc` | Timestamp no formato correto |

Meta: 9 testes verdes via `pytest -q`. Total esperado do projeto após esse PR: ~66 testes.

## Fora de escopo

Explícito para não haver pressão de escopo durante o PR:

- Retrieval / busca nos chunks → issue #3
- GitBook interno autenticado → issue #4
- Confluence SUP scraper → issue #6 a criar
- Integração com prompt do Gemini → issue #3
- Rerun incremental (só páginas modificadas) → V1.2+
- GitHub Actions semanal → V1.2+ (mencionado na issue mas adiar pra estabilizar primeiro)

## Critérios de aceite

Todos os da issue #2 +:

- [ ] `kiro fetch-gitbook --public` baixa toda a GitBook pública em <5min
- [ ] Cache JSON com 50-200 chunks no shape acima
- [ ] `fetched_at` em ISO 8601 UTC
- [ ] Falhas parciais não abortam o processo; são reportadas no fim
- [ ] Sem segredos no código (URL configurável)
- [ ] 9 testes novos verdes
- [ ] `.gitignore` ignora `kiro/data/*_cache.json`
- [ ] `.env.example` atualizado

## Pré-requisitos para começar a implementação

```bash
git checkout main && git pull
git checkout -b feature/gitbook-scraper
source .venv/bin/activate
pip install beautifulsoup4 respx  # respx é dev-only
```

`requirements.txt` ganha `beautifulsoup4`; `requirements-dev.txt` ganha `respx`.
