"""Facebook pelo navegador (Playwright + proxy SP). Sessão = storage_state; logado quando existe o cookie `c_user`."""
from __future__ import annotations

import time

from app.passos import Canal, ErroLogin, Passo
from app.redes.navegador import abrir, achar, digitar, guardar_falha, pausa, tem_cookie

CAMPO = [{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]


def _logado(ctx) -> bool:
    return tem_cookie(ctx, "c_user", "facebook.com")


def _aceitar_cookies(page) -> None:
    b = achar(page, ["button:has-text('Permitir todos os cookies')", "button:has-text('Allow all cookies')", "[data-cookiebanner=accept_button]"], 3)
    if b:
        b.click()
        pausa()


def login(canal: Canal, usuario: str, senha: str, proxy: str = "") -> tuple[dict, dict]:
    with abrir(proxy) as (ctx, page):
        page.goto("https://www.facebook.com/login/", wait_until="domcontentloaded")
        _aceitar_cookies(page)
        e = achar(page, ["#email", "input[name=email]"], 20)
        if not e:
            guardar_falha(page, "facebook-login")
            raise ErroLogin("rede_fora")
        digitar(e, usuario)
        digitar(achar(page, ["#pass", "input[name=pass]", "input[type=password]"], 10), senha)
        pausa()
        achar(page, ["button[name=login]", "#loginbutton", 'internal:role=button[name="Entrar"s]', 'internal:role=button[name="Log in"s]', "input[type=submit]"], 10).click()
        fim = time.time() + 180
        while time.time() < fim:
            pausa(1, 1.5)
            if _logado(ctx) and "checkpoint" not in page.url and "two_step" not in page.url:
                break
            if achar(page, ["text=/senha que você inseriu está incorreta|password you.ve entered is incorrect|esqueceu a senha\\?/i"], 0.5) and "login" in page.url:
                raise ErroLogin("senha_errada")
            cod = achar(page, ["input[name=approvals_code]", "input[autocomplete=one-time-code]", "input[type=text][inputmode=numeric]"], 0.5)
            if cod:
                v = canal.pedir(Passo("codigo_2fa", mensagem="Digite o código do app autenticador, do SMS ou do WhatsApp que o Facebook mandou.", campos=CAMPO))
                digitar(cod, v.strip())
                cont = achar(page, ["button:has-text('Continuar')", "button:has-text('Continue')", "#checkpointSubmitButton", "button[type=submit]"], 5)
                if cont:
                    cont.click()
                continue
            if achar(page, ["text=/Verifique as notificações|Check your notifications|aprove o login|Approve your login|outro dispositivo|another device/i"], 0.5):
                canal.mostrar(Passo("aprovar_no_celular", mensagem="Abra o Facebook no celular e aprove o acesso.", espera_s=3))
                continue
            salvar = achar(page, ["button:has-text('Salvar navegador')", "button:has-text('Save browser')", "button:has-text('Confiar neste dispositivo')", "button:has-text('Trust this device')"], 0.5)
            if salvar:
                salvar.click()
                continue
            if achar(page, ["iframe[src*=captcha]", "text=/captcha|não é um robô|not a robot/i"], 0.5):
                guardar_falha(page, "facebook-captcha")
                raise ErroLogin("captcha")
        else:
            guardar_falha(page, "facebook-prazo")
            raise TimeoutError()
        page.goto("https://www.facebook.com/me", wait_until="domcontentloaded")
        pausa(2, 3)
        h1 = achar(page, ["h1"], 8)
        return ctx.storage_state(), {"url": page.url, "nome": h1.inner_text().strip() if h1 else ""}


def ler_perfil(sessao: dict, proxy: str = "") -> dict:
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.facebook.com/me", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx) or "/login" in page.url:
            raise ErroLogin("sessao_caiu")
        h1 = achar(page, ["h1"], 10)
        return {"url": page.url, "nome": h1.inner_text().strip() if h1 else ""}


def publicar(sessao: dict, proxy: str, post: dict) -> dict:
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx) or "/login" in page.url:
            raise ErroLogin("sessao_caiu")
        abre = achar(page, ["div[role=button]:has-text('No que você está pensando')", "div[role=button]:has-text(\"What's on your mind\")"], 15)
        if not abre:
            guardar_falha(page, "facebook-sem-composer")
            raise RuntimeError("não achei o campo de publicação")
        abre.click()
        caixa = achar(page, ["div[role=dialog] div[role=textbox][contenteditable=true]"], 15)
        if not caixa:
            guardar_falha(page, "facebook-sem-editor")
            raise RuntimeError("não achei o editor")
        digitar(caixa, post.get("legenda") or "")
        arqs = post.get("arquivos") or []
        if arqs:
            foto = achar(page, ["div[role=dialog] [aria-label='Foto/vídeo']", "div[role=dialog] [aria-label='Photo/video']"], 8)
            if foto:
                with page.expect_file_chooser() as fc:
                    foto.click()
                fc.value.set_files(arqs[:10])
            else:
                page.locator("div[role=dialog] input[type=file]").first.set_input_files(arqs[:10])
            pausa(4, 6)
        prox = achar(page, ["div[role=dialog] div[role=button][aria-label='Avançar']", "div[role=dialog] div[role=button][aria-label='Next']"], 3)
        if prox:
            prox.click()
            pausa()
        pub = achar(page, ["div[role=dialog] div[role=button][aria-label='Publicar']", "div[role=dialog] div[role=button][aria-label='Post']"], 30)
        if not pub:
            guardar_falha(page, "facebook-sem-publicar")
            raise RuntimeError("não achei o botão Publicar")
        pub.click()
        pausa(5, 8)
        return {"ok": True, "link": "https://www.facebook.com/me"}


def aplicar(sessao: dict, proxy: str, proposta: dict) -> dict:
    return {k: "so_pelo_app" for k in proposta}
