"""TikTok pelo navegador (Playwright + proxy SP). Login pelo QR da página (a pessoa lê com o app); sessão = storage_state
(cookie `sessionid`). Publicação pelo TikTok Studio (upload de vídeo + legenda)."""
from __future__ import annotations

import time

from app.passos import Canal, ErroLogin, Passo
from app.redes.navegador import abrir, achar, digitar, guardar_falha, imagem, pausa, tem_cookie


def _logado(ctx) -> bool:
    return tem_cookie(ctx, "sessionid", "tiktok.com")


TEXTO_VERIFICACAO = ("text=/verifique sua identidade|confirme se é realmente você|confirme que é você|verify it.s (really )?you|"
                     "verify your identity|verificar identidade|security verification|verificação de segurança/i")
CAMPO_CODIGO = ["input[autocomplete=one-time-code]", "input[placeholder*=código i]", "input[placeholder*=code i]", "input[maxlength='6']",
                "input[name*=code i]"]
METODOS = r"/^\s*(e-?mail|sms|telefone|phone|número de telefone|phone number|mensagem de texto|text message)/i"
BOTAO_SEGUIR = ['internal:role=button[name=/^(enviar código|send code|enviar|send|avançar|next|verificar|verify|continuar|continue|confirmar|confirm|enviar)$/i]']


def _verificacao(page) -> bool:
    try:
        return page.locator(TEXTO_VERIFICACAO).count() > 0
    except Exception:  # noqa: BLE001
        return False


def _resolver_verificacao(page, canal: Canal) -> None:
    """Verificação de identidade depois do QR: código (e-mail/SMS), escolha do método ou, se for outro layout, a pessoa toca
    no lugar certo do print da página (passo captcha)."""
    from app.redes.navegador import resolver_tela_com_a_pessoa
    cod = achar(page, CAMPO_CODIGO, 1)
    if cod:
        v = canal.pedir(Passo("codigo_email", mensagem="O TikTok mandou um código (e-mail ou SMS) para confirmar que é você. Digite aqui.",
                              campos=[{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]))
        digitar(cod, v.strip())
        pausa(0.6, 1)
        ok = achar(page, BOTAO_SEGUIR, 4)
        if ok:
            ok.click()
        pausa(3, 4)
        return
    try:
        metodos = page.locator(f"internal:text={METODOS}").all()
        nomes = [m.inner_text().strip().split("\n")[0][:60] for m in metodos if m.is_visible()]
    except Exception:  # noqa: BLE001
        metodos, nomes = [], []
    if nomes:
        esc = canal.pedir(Passo("escolha", mensagem="O TikTok quer confirmar que é você. Por onde mandar o código?", opcoes=nomes))
        alvo = next((m for m, n in zip(metodos, nomes) if n == esc), metodos[0])
        alvo.click()
        pausa(1, 1.5)
        envio = achar(page, BOTAO_SEGUIR, 3)
        if envio:
            envio.click()
        pausa(3, 4)
        return
    resolver_tela_com_a_pessoa(page, canal, "O TikTok pediu para confirmar que é você. Toque na imagem onde precisa (ex.: no botão de verificar).")
    pausa(3, 4)


def login(canal: Canal, usuario: str = "", senha: str = "", proxy: str = "") -> tuple[dict, dict]:
    with abrir(proxy) as (ctx, page):
        page.goto("https://www.tiktok.com/login/qrcode", wait_until="domcontentloaded")
        fim = time.time() + 240
        ultimo = 0.0
        while time.time() < fim:
            if canal.cancelado():
                raise TimeoutError()
            if _logado(ctx):
                break
            if _verificacao(page):  # depois do QR o TikTok às vezes pede "confirme que é você"
                _resolver_verificacao(page, canal)
                ultimo = time.time()
                fim = max(fim, time.time() + 120)  # a verificação come tempo: dá mais prazo
                continue
            if time.time() - ultimo > 20:  # QR se renova; manda a imagem nova a cada 20 s
                qr = achar(page, ["canvas", "div[data-e2e=qr-code] img", "img[alt*=QR]"], 15)
                if not qr:
                    guardar_falha(page, "tiktok-sem-qr")
                    raise ErroLogin("rede_fora")
                canal.mostrar(Passo("qr", mensagem="No app do TikTok: Perfil → menu (☰) → leitor de QR. Leia este código.", imagem=imagem(page, qr), espera_s=3))
                ultimo = time.time()
            pausa(1.5, 2)
        else:
            raise TimeoutError()
        page.goto("https://www.tiktok.com/profile", wait_until="domcontentloaded")
        pausa(2, 3)
        u = achar(page, ["h1[data-e2e=user-title]", "[data-e2e=user-title]"], 8)
        return ctx.storage_state(), {"usuario": u.inner_text().strip() if u else "", "url": page.url}


def ler_perfil(sessao: dict, proxy: str = "") -> dict:
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.tiktok.com/profile", wait_until="domcontentloaded")
        pausa(2, 3)
        if not _logado(ctx):
            raise ErroLogin("sessao_caiu")
        u = achar(page, ["h1[data-e2e=user-title]", "[data-e2e=user-title]"], 8)
        bio = achar(page, ["h2[data-e2e=user-bio]"], 3)
        return {"usuario": u.inner_text().strip() if u else "", "bio": bio.inner_text().strip() if bio else "", "url": page.url}


def publicar(sessao: dict, proxy: str, post: dict) -> dict:
    arqs = post.get("arquivos") or []
    if post.get("tipo") != "video" or not arqs:
        raise ValueError("o TikTok precisa de um vídeo")
    with abrir(proxy, sessao) as (ctx, page):
        page.goto("https://www.tiktok.com/tiktokstudio/upload?from=upload", wait_until="domcontentloaded")
        pausa(3, 4)
        if not _logado(ctx):
            raise ErroLogin("sessao_caiu")
        page.locator("input[type=file]").first.set_input_files(arqs[0])
        ed = achar(page, ["div.public-DraftEditor-content[contenteditable=true]", "div[contenteditable=true]"], 120)
        if not ed:
            guardar_falha(page, "tiktok-sem-editor")
            raise RuntimeError("o upload não terminou")
        ed.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        digitar(ed, (post.get("legenda") or "")[:2000])
        pub = achar(page, ["button[data-e2e=post_video_button]", "button:has-text('Publicar')", "button:has-text('Post')"], 180)
        if not pub:
            guardar_falha(page, "tiktok-sem-publicar")
            raise RuntimeError("não achei o botão Publicar")
        for _ in range(60):  # o botão só habilita quando o processamento termina
            if pub.is_enabled():
                break
            time.sleep(2)
        pub.click()
        pausa(5, 8)
        return {"ok": True, "link": "https://www.tiktok.com/profile"}


def aplicar(sessao: dict, proxy: str, proposta: dict) -> dict:
    return {k: "so_pelo_app" for k in proposta}
