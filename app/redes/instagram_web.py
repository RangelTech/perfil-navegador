"""Instagram pelo navegador (Playwright + proxy SP). Substitui o instagrapi no login desde 15/11/2026: o Instagram parou de mandar
o cabeçalho `ig-set-password-encryption-key-id` e o instagrapi (2.18 e 3.1) quebra antes de tentar a senha.
Sessão = storage_state (cookie `sessionid`)."""
from __future__ import annotations

import time

from app.passos import Canal, ErroLogin, Passo
from app.redes.navegador import abrir, achar, digitar, em_desafio, guardar_falha, pausa, resolver_com_a_pessoa, tem_cookie

CAMPO = [{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]
AGORA_NAO = ["div[role=button]:has-text('Agora não')", "button:has-text('Agora não')", "div[role=button]:has-text('Not now')", "button:has-text('Not now')"]


def _logado(ctx) -> bool:
    return tem_cookie(ctx, "sessionid", "instagram.com")


def _cookies(page) -> None:
    b = achar(page, ["button:has-text('Permitir todos os cookies')", "button:has-text('Allow all cookies')"], 2)
    if b:
        b.click()
        pausa()


def login(canal: Canal, usuario: str, senha: str, proxy: str = "") -> tuple[dict, dict]:
    with abrir(proxy) as (ctx, page):
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
        _cookies(page)
        u = achar(page, ["input[name=username]", "input[name=email]", "input[autocomplete=username]"], 30)
        if not u and em_desafio(page):
            resolver_com_a_pessoa(page, canal)
            u = achar(page, ["input[name=username]", "input[name=email]"], 15)
        if not u:
            guardar_falha(page, "instagram-login")
            raise ErroLogin("rede_fora")
        digitar(u, usuario)
        digitar(achar(page, ["input[name=password]", "input[name=pass]", "input[type=password]"], 10), senha)
        pausa()
        achar(page, ["button[type=submit]", 'internal:role=button[name="Entrar"s]', 'internal:role=button[name="Log in"s]'], 10).click()
        fim = time.time() + 180
        while time.time() < fim:
            pausa(1.2, 1.8)
            if _logado(ctx):
                break
            if achar(page, ["text=/informações de login que você inseriu estão incorretas|senha (que você inseriu )?está incorreta|password (you entered )?(was|is) incorrect|login information you entered is incorrect/i"], 0.5):
                raise ErroLogin("senha_errada")
            cod = achar(page, ["input[name=verificationCode]", "input[name=security_code]", "input[autocomplete=one-time-code]"], 0.5)
            if cod:
                tipo = "codigo_2fa" if "two_factor" in page.url else "codigo_email"
                v = canal.pedir(Passo(tipo, mensagem="O Instagram mandou um código (app autenticador, SMS ou e-mail). Digite aqui.", campos=CAMPO))
                digitar(cod, v.strip())
                ok = achar(page, ["button[type=submit]", 'internal:role=button[name="Confirmar"s]', 'internal:role=button[name="Confirm"s]', 'internal:role=button[name="Enviar"s]'], 5)
                if ok:
                    ok.click()
                continue
            if achar(page, ["text=/Confirme que é você|Confirm it.s you|aprove este login|approve this login|Verifique seu celular/i"], 0.5):
                envio = achar(page, ['internal:role=button[name="Enviar código"s]', 'internal:role=button[name="Send security code"s]', 'internal:role=button[name="Continuar"s]'], 2)
                if envio:
                    envio.click()
                    continue
                canal.mostrar(Passo("aprovar_no_celular", mensagem="Abra o Instagram no celular e confirme que foi você.", espera_s=3))
                continue
            if em_desafio(page):
                resolver_com_a_pessoa(page, canal)
                continue
        else:
            guardar_falha(page, "instagram-prazo")
            raise TimeoutError()
        nao = achar(page, AGORA_NAO, 6)  # "Salvar suas informações de login?"
        if nao:
            nao.click()
        return ctx.storage_state(), _ler(page)


def _ler(page) -> dict:
    page.goto("https://www.instagram.com/accounts/edit/", wait_until="domcontentloaded")
    pausa(2, 3)
    bio = achar(page, ["textarea#pepBio", "textarea[name=biography]", "textarea"], 10)
    usuario = ""
    try:
        usuario = page.evaluate("() => (document.querySelector('a[href^=\"/\"][role=link] span')||{}).textContent || ''")
    except Exception:  # noqa: BLE001
        pass
    return {"bio": bio.input_value() if bio else "", "usuario": usuario.strip(), "url": "https://www.instagram.com/"}


def ler_perfil(sessao: dict, proxy: str = "") -> dict:
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        pausa(1.5, 2.5)
        if not _logado(ctx) or "/accounts/login" in page.url:
            raise ErroLogin("sessao_caiu")
        return _ler(page)


def publicar(sessao: dict, proxy: str, post: dict) -> dict:
    arqs = post.get("arquivos") or []
    if not arqs:
        raise ValueError("o Instagram precisa de foto ou vídeo")
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx) or "/accounts/login" in page.url:
            raise ErroLogin("sessao_caiu")
        nao = achar(page, AGORA_NAO, 3)
        if nao:
            nao.click()
        criar = achar(page, ["svg[aria-label='Nova publicação']", "svg[aria-label='New post']", "a:has(svg[aria-label='Criar'])", "a:has(svg[aria-label='Create'])"], 15)
        if not criar:
            guardar_falha(page, "instagram-sem-criar")
            raise RuntimeError("não achei o botão de criar")
        criar.click()
        pausa()
        sub = achar(page, ["a:has-text('Publicação')", "a:has-text('Post')", "span:text-is('Publicação')", "span:text-is('Post')"], 3)
        if sub:
            sub.click()
        page.locator("div[role=dialog] input[type=file], form input[type=file]").first.set_input_files(arqs[:10])
        for _ in range(2):  # recorte -> filtros
            av = achar(page, ['div[role=dialog] internal:role=button[name="Avançar"s]', 'div[role=dialog] internal:role=button[name="Next"s]',
                              "div[role=dialog] div[role=button]:text-is('Avançar')", "div[role=dialog] div[role=button]:text-is('Next')"], 60)
            if not av:
                guardar_falha(page, "instagram-sem-avancar")
                raise RuntimeError("o upload não avançou")
            av.click()
            pausa(1.5, 2.5)
        leg = achar(page, ["div[role=dialog] div[contenteditable=true][role=textbox]", "div[role=dialog] textarea"], 20)
        if leg and post.get("legenda"):
            digitar(leg, post["legenda"][:2200])
        comp = achar(page, ['div[role=dialog] internal:role=button[name="Compartilhar"s]', 'div[role=dialog] internal:role=button[name="Share"s]',
                            "div[role=dialog] div[role=button]:text-is('Compartilhar')", "div[role=dialog] div[role=button]:text-is('Share')"], 20)
        if not comp:
            guardar_falha(page, "instagram-sem-compartilhar")
            raise RuntimeError("não achei o botão Compartilhar")
        comp.click()
        if not achar(page, ["text=/foi compartilhad|has been shared|Seu reel foi|Your reel has/i"], 240):
            guardar_falha(page, "instagram-sem-confirmacao")
            raise RuntimeError("o Instagram não confirmou a publicação")
        return {"ok": True, "link": "https://www.instagram.com/"}


def aplicar(sessao: dict, proxy: str, proposta: dict) -> dict:
    """Na web dá para trocar a bio (Editar perfil). Nome e link ficam na Central de Contas / app."""
    out = {k: "so_pelo_app" for k in proposta}
    if "bio" not in proposta:
        return out
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.instagram.com/accounts/edit/", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx) or "/accounts/login" in page.url:
            raise ErroLogin("sessao_caiu")
        bio = achar(page, ["textarea#pepBio", "textarea[name=biography]", "textarea"], 15)
        if not bio:
            guardar_falha(page, "instagram-sem-bio")
            out["bio"] = "falhou"
            return out
        bio.fill("")
        digitar(bio, proposta["bio"][:150])
        env = achar(page, ['internal:role=button[name="Enviar"s]', 'internal:role=button[name="Submit"s]', "div[role=button]:text-is('Enviar')", "button[type=submit]"], 10)
        if not env:
            out["bio"] = "falhou"
            return out
        env.click()
        out["bio"] = "ok" if achar(page, ["text=/Perfil salvo|Profile saved/i"], 15) else "falhou"
        return out
