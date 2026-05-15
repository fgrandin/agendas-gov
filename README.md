# 📅 Agendas do Governo Federal Brasileiro

Aplicativo Streamlit que raspa e exibe os **compromissos públicos** das principais autoridades do Poder Executivo Federal para qualquer data selecionada.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

## Autoridades monitoradas

| Sigla | Autoridade | Fonte |
|-------|-----------|-------|
| — | Presidente da República | gov.br/planalto |
| — | Vice-Presidente da República | gov.br/planalto |
| MME | Ministro de Minas e Energia | e-Agendas / CGU |
| MF | Ministro da Fazenda | e-Agendas / CGU |
| MDIC | Ministro do Desenvolvimento, Indústria, Comércio e Serviços | e-Agendas / CGU |
| MMA | Ministro do Meio Ambiente e Mudança do Clima | e-Agendas / CGU |
| ANP | Todos os Diretores da ANP | e-Agendas / CGU |
| ANEEL | Todos os Diretores da ANEEL | e-Agendas / CGU |

---

## Funcionalidades

- Seleção de data via calendário (padrão: amanhã)
- Raspagem automática de duas fontes oficiais
- Exibição organizada por autoridade
- Filtro por autoridade e tipo de compromisso
- Métricas de resumo (total, reuniões, eventos)
- Download dos dados em JSON
- Descoberta dinâmica de diretores (ANP/ANEEL) — sem nomes fixos

---

## Como rodar localmente

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/agendas-gov.git
cd agendas-gov

# 2. Instale as dependências Python
pip install -r requirements.txt

# 3. Instale o Chromium do Playwright
playwright install chromium

# 4. Rode o app
streamlit run app.py
```

### Usar como script CLI

```bash
python scraper.py
# Gera agendas_YYYY-MM-DD.json com os compromissos de amanhã
```

---

## Deploy no Streamlit Community Cloud

1. Faça fork / push deste repositório para o seu GitHub.
2. Acesse [share.streamlit.io](https://share.streamlit.io) e conecte o repositório.
3. Defina **Main file path** como `app.py`.
4. Clique em **Deploy**.

O arquivo `packages.txt` instala as dependências de sistema do Chromium automaticamente.  
O arquivo `requirements.txt` instala o Python SDK do Playwright.  
O Chromium é baixado na primeira execução via `playwright install chromium` (embutido no `app.py`).

---

## Arquitetura técnica

### Fontes de dados

| Fonte | Mecanismo |
|-------|-----------|
| `gov.br/planalto` | `requests` + `BeautifulSoup` (HTML estático); fallback Playwright |
| `eagendas.cgu.gov.br` | Playwright headless (SPA Angular) |

### Como o e-Agendas funciona (engenharia reversa)

O site é uma SPA Angular com dados carregados em duas etapas:

1. **Lista de agentes** — chamada AJAX via `axios` in-page:
   ```
   GET /pesquisa/agentes-publicos-obrigados-por-orgao/orgao/{id}/ativo/true
   ```

2. **Eventos de cada agente** — navegação para:
   ```
   GET /?filtro_servidor={pertenencia_id}&tipo_filtro=ap
   ```
   Os eventos ficam no escopo AngularJS (`scope.events`) e são filtrados por data.

### IDs dos órgãos

| Órgão | ID |
|-------|-----|
| MME | 661 |
| MF | 1384 |
| MDIC | 1399 |
| MMA | 647 |
| ANP | 1176 |
| ANEEL | 1169 |

---

## Estrutura do repositório

```
agendas-gov/
├── app.py              # Streamlit UI
├── scraper.py          # Módulo de raspagem
├── requirements.txt    # Dependências Python
├── packages.txt        # Dependências de sistema (Streamlit Cloud)
├── .streamlit/
│   └── config.toml     # Tema e configurações
├── .gitignore
└── README.md
```

---

## Formato de saída (JSON)

```json
[
  {
    "autoridade": "Ministro(a) — Ministério de Minas e Energia",
    "orgao": "Ministério de Minas e Energia",
    "data": "2026-05-15",
    "hora_inicio": "10:00",
    "hora_fim": "11:00",
    "tipo": "Reunião",
    "assunto": "Discussão sobre marco regulatório do gás",
    "local": "MME, 8º andar",
    "participantes": ["Nome Sobrenome", "Outro Participante"]
  }
]
```

---

## Licença

Dados públicos coletados de fontes governamentais oficiais.  
Código sob licença MIT.
