"""LinkedIn pelo navegador (Playwright + proxy SP). Sessão = storage_state; cookie de sessão `li_at`."""
from __future__ import annotations

import time

from app.passos import Canal, ErroLogin, Passo
from app.redes.navegador import abrir, achar, digitar, em_desafio, guardar_falha, pausa, resolver_com_a_pessoa, tem_cookie

CAMPO = [{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]


def _logado(ctx, page) -> bool:
    return tem_cookie(ctx, "li_at", "linkedin.com") and "/checkpoint" not in page.url and "/login" not in page.url


def login(canal: Canal, usuario: str, senha: str, proxy: str = "") -> tuple[dict, dict]:
    with abrir(proxy) as (ctx, page):
        page.goto("https://www.linkedin.com/login?trk=guest_homepage", wait_until="domcontentloaded")
        CAMPOS_USUARIO = ["#username", "input[name=session_key]", "input[type=email]", "input[autocomplete=username]"]
        u = achar(page, CAMPOS_USUARIO, 45)
        if not u and em_desafio(page):
            resolver_com_a_pessoa(page, canal)
            u = achar(page, CAMPOS_USUARIO, 20)
        if not u:
            guardar_falha(page, "linkedin-login")
            raise ErroLogin("rede_fora")
        digitar(u, usuario)
        digitar(achar(page, ["#password", "input[name=session_password]", "input[type=password]"], 10), senha)
        pausa()
        achar(page, ["button[type=submit]", 'internal:role=button[name="Entrar"s]', 'internal:role=button[name="Sign in"s]'], 10).click()
        fim = time.time() + 180
        while time.time() < fim:
            pausa(1, 1.5)
            if _logado(ctx, page):
                break
            if achar(page, ["#error-for-password", "#error-for-username"], 0.5):
                raise ErroLogin("senha_errada")
            pin = achar(page, ["input[name=pin]", "#input__email_verification_pin", "#input__phone_verification_pin"], 0.5)
            if pin:
                cod = canal.pedir(Passo("codigo_email", mensagem="O LinkedIn mandou um código para o seu e-mail ou celular.", campos=CAMPO))
                digitar(pin, cod.strip())
                page.locator("#email-pin-submit-button, #two-step-submit-button, button[type=submit]").first.click()
                continue
            if achar(page, ["text=/Verifique seu app|Check your LinkedIn app|aprove|approve/i"], 0.5):
                canal.mostrar(Passo("aprovar_no_celular", mensagem="Abra o app do LinkedIn no celular e confirme o acesso.", espera_s=3))
                continue
            cap = achar(page, ["iframe[src*=captcha]", "#captcha-internal"], 0.5)
            if cap:
                guardar_falha(page, "linkedin-captcha")
                raise ErroLogin("captcha")
        else:
            guardar_falha(page, "linkedin-prazo")
            raise TimeoutError()
        page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded")
        pausa(2, 3)
        h1 = achar(page, ["h1"], 8)
        return ctx.storage_state(), {"url": page.url, "nome": h1.inner_text().strip() if h1 else ""}


def ler_perfil(sessao: dict, proxy: str = "") -> dict:
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx, page):
            raise ErroLogin("sessao_caiu")
        h1 = achar(page, ["h1"], 10)
        titulo = achar(page, ["div.text-body-medium", "[data-generated-suggestion-target]"], 4)
        return {"url": page.url, "nome": h1.inner_text().strip() if h1 else "", "titulo": titulo.inner_text().strip() if titulo else ""}


def publicar(sessao: dict, proxy: str, post: dict) -> dict:
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx, page):
            raise ErroLogin("sessao_caiu")
        btn = achar(page, ["button:has-text('Começar publicação')", "button:has-text('Start a post')", "button.share-box-feed-entry__trigger"], 15)
        if not btn:
            guardar_falha(page, "linkedin-sem-botao")
            raise RuntimeError("não achei o botão de publicar")
        btn.click()
        ed = achar(page, ["div.ql-editor[contenteditable=true]", "div[role=textbox][contenteditable=true]"], 15)
        if not ed:
            guardar_falha(page, "linkedin-sem-editor")
            raise RuntimeError("não achei o editor")
        digitar(ed, post.get("legenda") or "")
        arqs = post.get("arquivos") or []
        if arqs:
            midia = achar(page, ["button[aria-label*='mídia']", "button[aria-label*='media']", "button[aria-label*='foto']", "button[aria-label*='photo']"], 8)
            if midia:
                with page.expect_file_chooser() as fc:
                    midia.click()
                fc.value.set_files(arqs[:9])
            else:
                page.locator("input[type=file]").first.set_input_files(arqs[:9])
            pausa(3, 5)
            prox = achar(page, ["button:has-text('Avançar')", "button:has-text('Next')", "button:has-text('Concluído')", "button:has-text('Done')"], 30)
            if prox:
                prox.click()
                pausa()
        pub = achar(page, ["button.share-actions__primary-action", "button:has-text('Publicar')", "button:has-text('Post')"], 30)
        if not pub:
            guardar_falha(page, "linkedin-sem-publicar")
            raise RuntimeError("não achei o botão Publicar")
        pub.click()
        pausa(4, 6)
        return {"ok": True, "link": "https://www.linkedin.com/in/me/recent-activity/all/"}


def aplicar(sessao: dict, proxy: str, proposta: dict) -> dict:
    """Título e sobre têm formulário estável; o resto da suíte usa links diretos de edição (painel do Perfilaí)."""
    return {k: "so_pelo_app" for k in proposta}

