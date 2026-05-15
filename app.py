"""
app.py — Streamlit · Agendas do Governo Federal Brasileiro
===========================================================
Exibe os compromissos públicos das principais autoridades do Poder Executivo.
"""

import datetime
import io
import json
from collections import defaultdict

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Agendas do Governo Federal",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

from scraper import run_scraper, ORGAOS, PLANALTO_URLS

# ---------------------------------------------------------------------------
# Estilos CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .evento-card {
        background: #f8f9fa;
        border-left: 4px solid #1f6feb;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
    }
    .hora-badge {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1f6feb;
    }
    .tipo-badge {
        display: inline-block;
        background: #e8f4f8;
        color: #0969da;
        border-radius: 12px;
        padding: 2px 10px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .autoridade-header {
        background: linear-gradient(90deg, #0d1117 0%, #1f2937 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        margin: 1.5rem 0 0.5rem 0;
        font-size: 1rem;
        font-weight: 700;
    }
</style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image(
        "https://www.gov.br/static/images/govbr-colorido.svg",
        width=120,
    )
    st.title("📅 Agendas Gov")
    st.caption("Compromissos públicos do Executivo Federal")
    st.divider()

    amanha = datetime.date.today() + datetime.timedelta(days=1)
    data_sel = st.date_input(
        "📆 Selecione a data",
        value=amanha,
        min_value=datetime.date.today() - datetime.timedelta(days=90),
        max_value=datetime.date.today() + datetime.timedelta(days=30),
        format="DD/MM/YYYY",
    )
    data_str = str(data_sel)

    st.divider()
    buscar = st.button("🔍 Buscar Agendas", type="primary", use_container_width=True)

    st.divider()
    st.caption("**Fontes:**")
    st.caption("• [gov.br/planalto](https://www.gov.br/planalto)")
    st.caption("• [eagendas.cgu.gov.br](https://eagendas.cgu.gov.br)")
    st.divider()
    st.caption("**Autoridades monitoradas:**")
    for sigla, info in ORGAOS.items():
        st.caption(f"• {sigla} — {info['nome'][:35]}…" if len(info['nome']) > 35 else f"• {sigla} — {info['nome']}")
    for aut in PLANALTO_URLS:
        st.caption(f"• {aut}")

# ---------------------------------------------------------------------------
# Cabeçalho principal
# ---------------------------------------------------------------------------
st.title("📅 Agendas do Governo Federal")
st.caption(
    "Compromissos públicos das principais autoridades do Poder Executivo Federal Brasileiro."
)

data_br = data_sel.strftime("%d/%m/%Y") + (
    " *(amanhã)*" if data_sel == amanha else ""
)
st.info(f"Data selecionada: **{data_br}**", icon="📆")

# ---------------------------------------------------------------------------
# Execução do scraper
# ---------------------------------------------------------------------------
def _fazer_scraping(data: str):
    mensagens = []
    log_placeholder = st.empty()

    def cb(msg: str):
        mensagens.append(msg)
        log_placeholder.markdown(
            "\n".join(f"- {m}" for m in mensagens[-6:])
        )

    with st.spinner("⏳ Buscando agendas… (pode levar alguns minutos)"):
        compromissos = run_scraper(data, progress_callback=cb)

    log_placeholder.empty()
    st.session_state["compromissos"] = compromissos
    st.session_state["data_carregada"] = data
    return compromissos


if buscar:
    compromissos = _fazer_scraping(data_str)

compromissos = None
if (
    "compromissos" in st.session_state
    and st.session_state.get("data_carregada") == data_str
):
    compromissos = st.session_state["compromissos"]

# ---------------------------------------------------------------------------
# Exibição dos resultados
# ---------------------------------------------------------------------------
if compromissos is None:
    st.markdown(
        """
        ### Como usar
        1. Selecione a data na barra lateral (padrão: amanhã).
        2. Clique em **🔍 Buscar Agendas**.
        3. Aguarde — a coleta demora cerca de 1-2 minutos.

        > As agendas são publicadas pelos próprios órgãos, geralmente no dia anterior
        > ou no próprio dia. Se não encontrar eventos futuros, tente novamente mais tarde.
        """
    )
    st.stop()

if not compromissos:
    st.warning(
        f"⚠️ Nenhum compromisso público encontrado para **{data_sel.strftime('%d/%m/%Y')}**.\n\n"
        "As agendas podem ainda não ter sido publicadas. Tente novamente mais tarde.",
        icon="⚠️",
    )
    st.stop()

# ---------------------------------------------------------------------------
# Métricas de resumo
# ---------------------------------------------------------------------------
por_autoridade = defaultdict(list)
for c in compromissos:
    por_autoridade[c["autoridade"]].append(c)

tipos_count = defaultdict(int)
for c in compromissos:
    tipos_count[c.get("tipo", "Outro")] += 1

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de compromissos", len(compromissos))
col2.metric("Autoridades com agenda", len(por_autoridade))
col3.metric("Reuniões / Audiências", tipos_count.get("Reunião", 0) + tipos_count.get("Audiência pública", 0))
col4.metric("Eventos / Outros", len(compromissos) - tipos_count.get("Reunião", 0) - tipos_count.get("Audiência pública", 0))

st.divider()

# ---------------------------------------------------------------------------
# Filtros rápidos
# ---------------------------------------------------------------------------
todas_autoridades = sorted(por_autoridade.keys())
todos_tipos = sorted(set(c.get("tipo", "Outro") for c in compromissos))

col_f1, col_f2 = st.columns(2)
with col_f1:
    filtro_aut = st.multiselect(
        "🏛️ Filtrar por autoridade",
        options=todas_autoridades,
        default=[],
        placeholder="Todas as autoridades",
    )
with col_f2:
    filtro_tipo = st.multiselect(
        "📋 Filtrar por tipo",
        options=todos_tipos,
        default=[],
        placeholder="Todos os tipos",
    )

comp_filtrados = compromissos
if filtro_aut:
    comp_filtrados = [c for c in comp_filtrados if c["autoridade"] in filtro_aut]
if filtro_tipo:
    comp_filtrados = [c for c in comp_filtrados if c.get("tipo") in filtro_tipo]

if not comp_filtrados:
    st.info("Nenhum compromisso encontrado com os filtros selecionados.")
    st.stop()

por_aut_filtrado = defaultdict(list)
for c in comp_filtrados:
    por_aut_filtrado[c["autoridade"]].append(c)

# ---------------------------------------------------------------------------
# Ícones por tipo
# ---------------------------------------------------------------------------
TIPO_ICONS = {
    "Reunião": "🤝",
    "Audiência pública": "🎤",
    "Evento": "📅",
    "Viagem": "✈️",
    "Compromisso": "📋",
    "Doação": "🎁",
    "Donativo": "🎁",
}


def tipo_icon(tipo: str) -> str:
    return TIPO_ICONS.get(tipo, "📌")


# ---------------------------------------------------------------------------
# Tabs principais
# ---------------------------------------------------------------------------
tab_cards, tab_planilha, tab_estruturado = st.tabs(
    ["📋 Compromissos", "📊 Planilha", "📄 Formato estruturado"]
)

# ── Tab 1: Cards ────────────────────────────────────────────────────────────
with tab_cards:
    col_dl, col_info = st.columns([2, 5])
    with col_dl:
        st.download_button(
            label="⬇️ Baixar JSON",
            data=json.dumps(comp_filtrados, ensure_ascii=False, indent=2),
            file_name=f"agendas_{data_str}.json",
            mime="application/json",
            use_container_width=True,
        )
    with col_info:
        st.caption(
            f"Arquivo `agendas_{data_str}.json` com {len(comp_filtrados)} compromisso(s)."
        )

    for autoridade in sorted(por_aut_filtrado.keys()):
        eventos = por_aut_filtrado[autoridade]
        st.markdown(
            f'<div class="autoridade-header">🏛️ {autoridade} &nbsp; '
            f'<span style="font-weight:400; font-size:0.85rem;">({len(eventos)} compromisso(s))</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

        for ev in eventos:
            hora = ev.get("hora_inicio") or "--:--"
            hora_fim = ev.get("hora_fim")
            hora_str = f"{hora} – {hora_fim}" if hora_fim else hora
            tipo = ev.get("tipo") or "Compromisso"
            assunto = ev.get("assunto") or "(sem descrição)"
            local = ev.get("local")
            participantes = ev.get("participantes") or []

            with st.container():
                c1, c2, c3 = st.columns([1.2, 1.5, 6])
                with c1:
                    st.markdown(f"**🕐 {hora_str}**")
                with c2:
                    st.markdown(
                        f'<span class="tipo-badge">{tipo_icon(tipo)} {tipo}</span>',
                        unsafe_allow_html=True,
                    )
                with c3:
                    st.markdown(f"**{assunto}**")
                    if local:
                        st.caption(f"📍 {local}")
                    if participantes:
                        with st.expander(f"👥 {len(participantes)} participante(s)"):
                            for p in participantes:
                                st.write(f"• {p}")

        st.markdown("---")

# ── Tab 2: Planilha ─────────────────────────────────────────────────────────
with tab_planilha:
    rows = []
    for c in comp_filtrados:
        rows.append({
            "Autoridade": c.get("autoridade", ""),
            "Nome": c.get("nome", ""),
            "Órgão": c.get("orgao", ""),
            "Data": c.get("data", ""),
            "Hora início": c.get("hora_inicio") or "",
            "Hora fim": c.get("hora_fim") or "",
            "Tipo": c.get("tipo") or "",
            "Assunto": c.get("assunto") or "",
            "Local": c.get("local") or "",
            "Participantes": "; ".join(c.get("participantes") or []),
        })

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Autoridade": st.column_config.TextColumn(width="medium"),
            "Assunto": st.column_config.TextColumn(width="large"),
            "Participantes": st.column_config.TextColumn(width="large"),
        },
    )

    col_csv, col_xlsx = st.columns(2)
    with col_csv:
        st.download_button(
            label="⬇️ Baixar CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"agendas_{data_str}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_xlsx:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Agendas")
        st.download_button(
            label="⬇️ Baixar Excel",
            data=buf.getvalue(),
            file_name=f"agendas_{data_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

# ── Tab 3: Formato estruturado ───────────────────────────────────────────────
with tab_estruturado:
    linhas = []
    for autoridade in sorted(por_aut_filtrado.keys()):
        eventos = por_aut_filtrado[autoridade]
        nome = eventos[0].get("nome", "") if eventos else ""
        cabecalho = f"{autoridade}  {nome}".strip() if nome and nome != autoridade else autoridade
        linhas.append(cabecalho)
        for ev in eventos:
            data_ev = ev.get("data") or ""
            tipo = ev.get("tipo") or ""
            hora = ev.get("hora_inicio") or ""
            assunto = ev.get("assunto") or ""
            local = ev.get("local") or ""
            partic = "; ".join(ev.get("participantes") or [])
            linha = "\t".join([data_ev, tipo, hora, assunto, local, partic])
            linhas.append(linha)
        linhas.append("")

    texto_estruturado = "\n".join(linhas)

    st.download_button(
        label="⬇️ Baixar .txt",
        data=texto_estruturado.encode("utf-8"),
        file_name=f"agendas_estruturado_{data_str}.txt",
        mime="text/plain",
    )

    st.text_area(
        label="",
        value=texto_estruturado,
        height=600,
        label_visibility="collapsed",
    )

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.caption(
    "Dados coletados automaticamente de fontes públicas oficiais. "
    "Desenvolvido com [Playwright](https://playwright.dev/) + "
    "[Streamlit](https://streamlit.io/)."
)
