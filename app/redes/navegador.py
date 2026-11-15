"""Base do Playwright (Chromium) para TikTok, LinkedIn e Facebook: proxy SP, idioma e fuso do Brasil, digitação com ritmo humano.

Cada login ou publicação abre o próprio navegador na thread que chamou (a API síncrona do Playwright é por thread)
e fecha ao terminar. A sessão guardada é o `storage_state` (cookies + localStorage).
"""
from __future__ import annotations

import base64
import os
import random
import time
from contextlib import contextmanager
from urllib.parse import urlparse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PASTA_FALHAS = os.path.join(os.environ.get("PN_DADOS", "/data"), "falhas")


def _proxy(url: str) -> dict | None:
    if not url:
        return None
    u = urlparse(url)
    p = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        p.update({"username": u.username, "password": u.password or ""})
    return p


@contextmanager
def abrir(proxy: str = "", estado: dict | None = None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # channel="chromium" = Chromium completo no modo "new headless" (o headless-shell é barrado pelo Cloudflare do LinkedIn)
        b = pw.chromium.launch(headless=os.environ.get("PN_VISIVEL") != "1", channel="chromium", proxy=_proxy(proxy),
                               args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = b.new_context(locale="pt-BR", timezone_id="America/Sao_Paulo", user_agent=UA, viewport={"width": 1366, "height": 900},
                            storage_state=estado or None)
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        try:
            yield ctx, page
        finally:
            ctx.close()
            b.close()


def pausa(a: float = 0.4, b: float = 1.2) -> None:
    time.sleep(random.uniform(a, b))


def digitar(loc, texto: str) -> None:
    loc.click()
    pausa(0.2, 0.5)
    loc.press_sequentially(texto, delay=random.randint(45, 110))


def achar(page, seletores: list[str], prazo_s: float = 10):
    """Primeiro seletor visível (aceita textos em português e inglês). None se nenhum aparecer no prazo."""
    fim = time.time() + prazo_s
    while time.time() < fim:
        for s in seletores:
            try:
                todos = page.locator(s)
                for i in range(min(todos.count(), 6)):  # o site pode ter cópias ocultas (layout móvel/desktop)
                    loc = todos.nth(i)
                    if loc.is_visible():
                        return loc
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.4)
    return None


def imagem(page, loc=None) -> str:
    png = (loc or page).screenshot(type="png")
    return "data:image/png;base64," + base64.b64encode(png).decode()


def guardar_falha(page, nome: str) -> None:
    """Print da tela onde quebrou (sem senha: os campos de senha ficam mascarados pelo próprio site). Fica só no volume."""
    try:
        os.makedirs(PASTA_FALHAS, exist_ok=True)
        page.screenshot(path=os.path.join(PASTA_FALHAS, f"{int(time.time())}-{nome}.png"))
    except Exception:  # noqa: BLE001
        pass


def tem_cookie(ctx, nome: str, dominio: str) -> bool:
    return any(c["name"] == nome and dominio in c["domain"] and c.get("value") for c in ctx.cookies())
