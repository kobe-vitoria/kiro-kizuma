# Deploy Kizuma no Render

Este projeto pode ser publicado como Web Service no Render para uso leve.

## 1) Pré-requisitos

- Repositório no GitHub com este código.
- Conta no Render.

## 2) Criar o serviço

1. No Render, clique em **New +** -> **Blueprint**.
2. Conecte o repositório.
3. O Render vai detectar o arquivo `render.yaml`.
4. Confirme a criação do serviço `kizuma`.

## 3) Variáveis sensíveis

No dashboard do serviço, configure variáveis por ambiente:

- `JIRA_BASE_URL`
- `JIRA_USER_EMAIL`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEY`
- `LLM_API_KEY`

Opcional:

- `LLM_PROVIDER` (`gemini` ou `anthropic`)
- `LLM_MODEL`
- `LLM_BASE_URL`
- `REL_ALL_HISTORY`
- `REL_LOOKBACK_MONTHS`
- `REL_LOOKBACK_DAYS`
- `REL_TICKET_LIMIT`

Para restringir acesso na URL publicada:

- `KIZUMA_BASIC_AUTH_USER`
- `KIZUMA_BASIC_AUTH_PASSWORD`

Quando essas duas variáveis existem, a app exige Basic Auth.

## 4) Frontend

O Render exibe o frontend normalmente.

Neste caso, o frontend é servido pela própria app Python em:

- `/` (formulário + resultado)
- `/download?file=...` (download Markdown)

## 5) Observações de segurança

- Não versionar tokens no repositório.
- Evitar compartilhar a URL sem autenticação.
- O output no Render está configurado para `/tmp/kizuma-output` (efêmero).

## 6) Deploy sem Blueprint (manual)

Se preferir criar serviço manualmente:

- Build Command: `pip install -r requirements.txt`
- Start Command: `python -m customer_health.webapp --host 0.0.0.0 --port $PORT`
- Runtime: Python 3.11

Depois configure as mesmas variáveis do item 3.
