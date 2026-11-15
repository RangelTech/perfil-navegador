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


def desafio_cloudflare(page) -> bool:
    """Se a página mostra o Turnstile ("Confirme que é humano"), clica na caixa como uma pessoa. True se clicou."""
    for f in page.frames:
        if "challenges.cloudflare.com" in (f.url or ""):
            try:
                caixa = f.frame_element().bounding_box()
            except Exception:  # noqa: BLE001
                return False
            if not caixa or caixa["width"] < 30:
                return False
            x = caixa["x"] + 28 + random.uniform(-3, 3)
            y = caixa["y"] + caixa["height"] / 2 + random.uniform(-3, 3)
            page.mouse.move(x - random.uniform(60, 120), y - random.uniform(20, 40))
            page.mouse.move(x, y, steps=random.randint(8, 16))
            pausa(0.2, 0.6)
            page.mouse.click(x, y)
            time.sleep(5)
            return True
    return False


def achar(page, seletores: list[str], prazo_s: float = 10):
    """Primeiro seletor visível (aceita textos em português e inglês). None se nenhum aparecer no prazo.
    Se no caminho aparecer o desafio do Cloudflare, clica nele e continua esperando."""
    fim = time.time() + prazo_s
    cliques = 0
    while time.time() < fim:
        if cliques < 3 and prazo_s >= 5 and desafio_cloudflare(page):
            cliques += 1
            fim = max(fim, time.time() + 15)
            continue
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


TEXTO_DESAFIO = "text=/Confirme que é humano|Verify you are human|Executando verificação de segurança|Performing security verification/i"


def em_desafio(page) -> bool:
    try:
        return page.locator(TEXTO_DESAFIO).count() > 0
    except Exception:  # noqa: BLE001
        return False


def resolver_com_a_pessoa(page, canal, tentativas: int = 3) -> None:
    """Passo `captcha`: manda o print da tela; a pessoa toca onde precisa ("x,y" em pixels do print) e o servidor clica ali."""
    from app.passos import Passo
    for _ in range(tentativas):
        if not em_desafio(page):
            return
        v = canal.pedir(Passo("captcha", mensagem="A rede pediu uma verificação. Toque na caixa 'Confirme que é humano' na imagem.",
                              imagem=imagem(page), campos=[{"id": "clique", "tipo": "clique", "rotulo": "Toque na imagem"}]))
        try:
            x, y = (float(n) for n in v.split(",")[:2])
        except ValueError:
            continue
        page.mouse.move(x - 40, y - 20)
        page.mouse.move(x, y, steps=10)
        page.mouse.click(x, y)
        time.sleep(6)
