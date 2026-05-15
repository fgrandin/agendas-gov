"""
scraper.py — Módulo de raspagem de agendas do Governo Federal Brasileiro
=========================================================================
Coleta compromissos públicos de D+1 (ou data fornecida) para:
  - Presidente da República        (gov.br/planalto)
  - Vice-Presidente da República   (gov.br/planalto)
  - Ministro de Minas e Energia    (eagendas.cgu.gov.br)
  - Ministro da Fazenda            (eagendas.cgu.gov.br)
  - Ministro do MDIC               (eagendas.cgu.gov.br)
  - Ministro do Meio Ambiente      (eagendas.cgu.gov.br)
  - Todos os Diretores da ANP      (eagendas.cgu.gov.br)
  - Todos os Diretores da ANEEL    (eagendas.cgu.gov.br)

API pública descoberta via engenharia reversa do e-Agendas (Angular SPA):
  GET /pesquisa/agentes-publicos-obrigados-por-orgao/orgao/{id}/ativo/true
  GET /?filtro_servidor={pertenencia_id}&tipo_filtro=ap  → events no scope Angular
"""

import asyncio
import datetime
import json
import logging
import re
import shutil
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = logging.getLogger(__name__)

MAX_CONCURRENT_PAGES = 4  # abas paralelas para buscar eventos


def _chromium_path() -> Optional[str]:
    """Retorna o caminho do Chromium do sistema, se disponível (Streamlit Cloud / Debian)."""
    for name in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome"):
        path = shutil.which(name)
        if path:
            log.info("Chromium do sistema encontrado: %s", path)
            return path
    return None

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
BASE_URL = "https://eagendas.cgu.gov.br"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

ORGAOS = {
    "MME": {
        "id": 661,
        "nome": "Ministério de Minas e Energia",
        "cargo_filtro": "MINISTRO",
        "tipo": "ministro",
    },
    "MF": {
        "id": 1384,
        "nome": "Ministério da Fazenda",
        "cargo_filtro": "MINISTRO",
        "tipo": "ministro",
    },
    "MDIC": {
        "id": 1399,
        "nome": "Ministério do Desenvolvimento, Indústria, Comércio e Serviços",
        "cargo_filtro": "MINISTRO",
        "tipo": "ministro",
    },
    "MMA": {
        "id": 647,
        "nome": "Ministério do Meio Ambiente e Mudança do Clima",
        "cargo_filtro": "MINISTRO",
        "tipo": "ministro",
    },
    "ANP": {
        "id": 1176,
        "nome": "Agência Nacional do Petróleo, Gás Natural e Biocombustíveis",
        "cargo_filtro": "DIRETOR",
        "tipo": "diretores",
    },
    "ANEEL": {
        "id": 1169,
        "nome": "Agência Nacional de Energia Elétrica",
        "cargo_filtro": "DIRETOR",
        "tipo": "diretores",
    },
}

PLANALTO_URLS = {
    "Presidente da República": (
        "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/"
        "agenda-do-presidente-da-republica-lula/"
        "agenda-do-presidente-da-republica/{data}"
    ),
    "Vice-Presidente da República": (
        "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/"
        "agenda-do-vice-presidente/agenda-do-vice-presidente/{data}"
    ),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_tomorrow() -> str:
    return str(datetime.date.today() + datetime.timedelta(days=1))


def parse_hora(dt_str: Optional[str]) -> Optional[str]:
    if not dt_str:
        return None
    if "T" in dt_str:
        return dt_str.split("T")[1][:5]
    return None


def parse_participantes(html_detalhe: Optional[str]) -> list:
    if not html_detalhe:
        return []
    soup = BeautifulSoup(html_detalhe, "lxml")
    nomes = []
    for linha in soup.get_text(separator="\n").splitlines():
        linha = linha.strip()
        if linha.startswith("- ") and len(linha) > 3:
            nome = linha[2:].split(" (CPF")[0].split(" /")[0].strip()
            if nome:
                nomes.append(nome)
    return nomes


def event_to_compromisso(evento: dict, autoridade: str, orgao: str, data: str) -> dict:
    hora_inicio = parse_hora(evento.get("start"))
    hora_fim = evento.get("hora_fim") or parse_hora(evento.get("end"))

    tipo = evento.get("tipo", "Compromisso")
    titulo = evento.get("title", "")
    assunto = titulo
    if " - " in titulo:
        partes = titulo.split(" - ", 1)
        if partes[0].lower() == tipo.lower():
            assunto = partes[1]

    detalhamento = evento.get("detalhamento_exibicao") or {}
    principal = detalhamento.get("principal") or assunto

    return {
        "autoridade": autoridade,
        "orgao": orgao,
        "data": data,
        "hora_inicio": hora_inicio,
        "hora_fim": hora_fim,
        "tipo": tipo,
        "assunto": principal or assunto,
        "local": evento.get("local"),
        "participantes": parse_participantes(evento.get("detalhe")),
    }


# ---------------------------------------------------------------------------
# Planalto — HTML estático (síncrono, rodado em thread)
# ---------------------------------------------------------------------------

def _scrape_planalto_sync(autoridade: str, url_template: str, data: str) -> list:
    url = url_template.format(data=data)
    log.info("[Planalto] %s → %s", autoridade, url)
    headers = {"User-Agent": UA}
    compromissos = []

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("[Planalto] %s indisponível (%s)", autoridade, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    itens = (
        soup.select("article.tileItem")
        or soup.select(".compromisso")
        or soup.select(".agenda-item")
        or soup.select("li.item")
    )

    if not itens:
        hora_re = re.compile(r"(\d{1,2}[h:]\d{2})\s+(.+)")
        for match in hora_re.finditer(soup.get_text(separator="\n")):
            hora_raw, descr = match.group(1), match.group(2).strip()
            hora = hora_raw.replace("h", ":") if "h" in hora_raw else hora_raw
            if len(descr) > 5:
                compromissos.append({
                    "autoridade": autoridade,
                    "nome": autoridade,
                    "orgao": "Presidência da República",
                    "data": data,
                    "hora_inicio": hora,
                    "hora_fim": None,
                    "tipo": "Compromisso",
                    "assunto": descr[:200],
                    "local": None,
                    "participantes": [],
                })
        return compromissos

    for item in itens:
        texto = item.get_text(separator=" ", strip=True)
        hora_match = re.search(r"(\d{1,2}[h:]\d{2})", texto)
        hora = hora_match.group(1).replace("h", ":") if hora_match else None
        descricao = re.sub(r"\d{1,2}[h:]\d{2}\s*", "", texto).strip()
        if descricao:
            compromissos.append({
                "autoridade": autoridade,
                "nome": autoridade,
                "orgao": "Presidência da República",
                "data": data,
                "hora_inicio": hora,
                "hora_fim": None,
                "tipo": "Compromisso",
                "assunto": descricao[:300],
                "local": None,
                "participantes": [],
            })

    log.info("[Planalto] %s: %d compromisso(s)", autoridade, len(compromissos))
    return compromissos


async def _scrape_planalto_playwright(autoridade: str, url: str, data: str, ctx: BrowserContext) -> list:
    """Fallback com Playwright usando o contexto já aberto."""
    log.info("[Planalto-PW] %s via Playwright", autoridade)
    compromissos = []
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(1)
        soup = BeautifulSoup(await page.content(), "lxml")
        hora_re = re.compile(r"(\d{1,2}[h:]\d{2})\s+(.+)")
        for match in hora_re.finditer(soup.get_text(separator="\n")):
            hora_raw, descr = match.group(1), match.group(2).strip()
            hora = hora_raw.replace("h", ":") if "h" in hora_raw else hora_raw
            if len(descr) > 5:
                compromissos.append({
                    "autoridade": autoridade,
                    "nome": autoridade,
                    "orgao": "Presidência da República",
                    "data": data,
                    "hora_inicio": hora,
                    "hora_fim": None,
                    "tipo": "Compromisso",
                    "assunto": descr[:200],
                    "local": None,
                    "participantes": [],
                })
    except Exception as exc:
        log.error("[Planalto-PW] Erro: %s", exc)
    finally:
        await page.close()
    return compromissos


async def _scrape_planalto_all(data: str, ctx: BrowserContext, cb: Optional[Callable]) -> list:
    """Busca Presidente e Vice em paralelo."""
    async def fetch(autoridade, url_tpl):
        if cb:
            cb(f"Buscando {autoridade} (Planalto)…")
        url = url_tpl.format(data=data)
        comp = await asyncio.to_thread(_scrape_planalto_sync, autoridade, url_tpl, data)
        if not comp:
            comp = await _scrape_planalto_playwright(autoridade, url, data, ctx)
        return comp

    results = await asyncio.gather(*[
        fetch(aut, tpl) for aut, tpl in PLANALTO_URLS.items()
    ])
    return [c for batch in results for c in batch]


# ---------------------------------------------------------------------------
# e-Agendas — Playwright (SPA Angular)
# ---------------------------------------------------------------------------

async def _get_agentes(page: Page, orgao_id: int) -> list:
    try:
        result = await page.evaluate(f"""
            async () => {{
                const r = await axios.get(
                    '/pesquisa/agentes-publicos-obrigados-por-orgao/orgao/{orgao_id}/ativo/true'
                );
                return r.data;
            }}
        """)
        return result if isinstance(result, list) else []
    except Exception as exc:
        log.error("[eAgendas] Falha agentes orgao=%d: %s", orgao_id, exc)
        return []


async def _get_events_page(
    ctx: BrowserContext,
    sem: asyncio.Semaphore,
    token: str,
    pid: int,
    cargo: str,
    data: str,
) -> list:
    """Abre uma aba própria para buscar eventos de um agente (paralelo-seguro)."""
    url = (
        f"{BASE_URL}/?_token={token}"
        "&filtro_orgaos_ativos=on&filtro_cargos_ativos=on&filtro_apos_ativos=on"
        "&cargo_confianca_id=&is_cargo_vago=false"
        f"&filtro_cargo={requests.utils.quote(cargo)}"
        f"&filtro_servidor={pid}&tipo_filtro=ap"
    )
    async with sem:
        page = await ctx.new_page()
        try:
            await page.goto(url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(1)
            events = await page.evaluate(f"""
                () => {{
                    try {{
                        const s = angular.element(document.getElementById('controller')).scope();
                        return (s.events || []).filter(e => (e.start || '').startsWith('{data}'));
                    }} catch(e) {{ return []; }}
                }}
            """)
            return events if isinstance(events, list) else []
        except Exception as exc:
            log.error("[eAgendas] Falha agenda pid=%d: %s", pid, exc)
            return []
        finally:
            await page.close()


async def _run_eagendas(data: str, ctx: BrowserContext, cb: Optional[Callable] = None) -> list:
    # Página base para chamar a API interna com axios (requer cookies do site)
    page = await ctx.new_page()
    if cb:
        cb("Abrindo e-Agendas…")
    await page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
    await asyncio.sleep(1)

    token = await page.evaluate(
        "() => { const el = document.querySelector('input[name=\"_token\"]'); "
        "return el ? el.value : ''; }"
    )
    if not token:
        log.error("[eAgendas] CSRF token não obtido.")
        await page.close()
        return []

    # Busca agentes de todos os órgãos em paralelo (chamadas axios na mesma página)
    if cb:
        cb("Buscando agentes de todos os órgãos…")
    all_agentes = await asyncio.gather(*[
        _get_agentes(page, info["id"]) for info in ORGAOS.values()
    ])
    await page.close()

    # Monta lista de trabalho: (autoridade, orgao_nome, pid, cargo, sigla)
    work_items = []
    for (sigla, info), agentes in zip(ORGAOS.items(), all_agentes):
        tipo = info["tipo"]
        orgao_nome = info["nome"]
        cargo_filtro = info["cargo_filtro"]

        if tipo == "ministro":
            titulares = sorted(
                [a for a in agentes
                 if (a.get("cargo") or "").upper().startswith(cargo_filtro)
                 and not a.get("fecha_termino")],
                key=lambda a: a["pertenencia_id"],
                reverse=True,
            )
            alvo = titulares[:1]
        else:
            alvo = [
                a for a in agentes
                if (a.get("cargo") or "").upper().startswith(cargo_filtro)
                and not a.get("fecha_termino")
            ]

        for agente in alvo:
            pid = agente["pertenencia_id"]
            nome = agente.get("nome", "Desconhecido")
            cargo = agente.get("cargo", "")
            if tipo == "ministro":
                autoridade = f"Ministro(a) — {orgao_nome}"
            else:
                autoridade = f"{sigla} — {nome} ({cargo})"
            work_items.append((autoridade, orgao_nome, pid, cargo, sigla, nome))

    log.info("[eAgendas] %d agentes identificados no total", len(work_items))

    # Busca eventos de todos os agentes em paralelo (máx MAX_CONCURRENT_PAGES abas)
    sem = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

    async def fetch_one(autoridade, orgao_nome, pid, cargo, sigla, nome):
        if cb:
            cb(f"[{sigla}] Buscando agenda de {nome}…")
        events = await _get_events_page(ctx, sem, token, pid, cargo, data)
        log.info("[eAgendas/%s] pid=%d → %d evento(s)", sigla, pid, len(events))
        compromissos = []
        for ev in events:
            if ev.get("tipo") == "Viagem SCDP":
                compromissos.append({
                    "autoridade": autoridade,
                    "nome": nome,
                    "orgao": orgao_nome,
                    "data": data,
                    "hora_inicio": None,
                    "hora_fim": None,
                    "tipo": "Viagem",
                    "assunto": ev.get("title", "Viagem SCDP"),
                    "local": None,
                    "participantes": [],
                })
            else:
                c = event_to_compromisso(ev, autoridade, orgao_nome, data)
                c["nome"] = nome
                compromissos.append(c)
        return compromissos

    results = await asyncio.gather(*[fetch_one(*item) for item in work_items])
    return [c for batch in results for c in batch]


# ---------------------------------------------------------------------------
# Interface pública
# ---------------------------------------------------------------------------

def consolidate(results: list) -> list:
    def sort_key(c):
        return (c.get("autoridade", ""), c.get("hora_inicio") or "99:99")
    return sorted(results, key=sort_key)


async def _async_main(data: str, cb: Optional[Callable] = None) -> list:
    async with async_playwright() as pw:
        launch_kw = {"headless": True}
        sys_chromium = _chromium_path()
        if sys_chromium:
            launch_kw["executable_path"] = sys_chromium
        browser: Browser = await pw.chromium.launch(**launch_kw)
        ctx: BrowserContext = await browser.new_context(user_agent=UA)

        # Planalto e e-Agendas rodam em paralelo
        planalto_task = asyncio.create_task(_scrape_planalto_all(data, ctx, cb))
        eagendas_task = asyncio.create_task(_run_eagendas(data, ctx, cb))

        planalto_comp, eagendas_comp = await asyncio.gather(planalto_task, eagendas_task)

        await browser.close()

    return consolidate(planalto_comp + eagendas_comp)


def run_scraper(data: Optional[str] = None, progress_callback: Optional[Callable] = None) -> list:
    """
    Ponto de entrada síncrono — compatível com Streamlit e CLI.

    Args:
        data: data no formato YYYY-MM-DD (padrão: amanhã)
        progress_callback: função f(msg: str) chamada a cada passo

    Returns:
        Lista de dicts com compromissos
    """
    if data is None:
        data = get_tomorrow()
    return asyncio.run(_async_main(data, progress_callback))


def main():
    """Entrada CLI: python scraper.py"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    data = get_tomorrow()
    log.info("Buscando agendas para %s", data)
    compromissos = run_scraper(data)

    data_br = datetime.datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")
    print(f"\n{'='*60}\nAGENDAS PARA {data_br}\n{'='*60}")
    atual = None
    for c in compromissos:
        if c["autoridade"] != atual:
            atual = c["autoridade"]
            print(f"\n[{atual.upper()}]")
        hora = c.get("hora_inicio") or "--:--"
        tipo = c.get("tipo") or "Compromisso"
        assunto = c.get("assunto") or "(sem descrição)"
        local_str = f" | {c['local']}" if c.get("local") else ""
        print(f"  {hora} | {tipo} | {assunto}{local_str}")

    print(f"\n{'='*60}")
    print(f"Total: {len(compromissos)} compromisso(s)")

    nome_arquivo = f"agendas_{data}.json"
    with open(nome_arquivo, "w", encoding="utf-8") as f:
        json.dump(compromissos, f, ensure_ascii=False, indent=2)
    print(f"Arquivo salvo: {nome_arquivo}\n{'='*60}\n")


if __name__ == "__main__":
    main()
