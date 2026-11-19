"""TikTok pelo navegador (Playwright + proxy SP). Login pelo QR da página (a pessoa lê com o app); sessão = storage_state
(cookie `sessionid`). Publicação pelo TikTok Studio (upload de vídeo + legenda)."""
from __future__ import annotations

import re
import time

from app.passos import Canal, ErroLogin, Passo
from app.redes.navegador import abrir, achar, digitar, guardar_falha, imagem, pausa, tem_cookie


def _logado(ctx) -> bool:
    return tem_cookie(ctx, "sessionid", "tiktok.com")


TEXTO_VERIFICACAO = ("text=/verifique se é realmente você|verifique sua identidade|confirme se é realmente você|confirme que é você|verify it.s (really )?you|"
                     "verify your identity|verificar identidade|security verification|verificação de segurança/i")
CAMPO_CODIGO = ["input[autocomplete=one-time-code]", "input[placeholder*=código i]", "input[placeholder*=code i]", "input[maxlength='6']",
                "input[name*=code i]"]
BOTAO_SEGUIR = ['internal:role=button[name=/^(enviar código|send code|enviar|send|avançar|next|verificar|verify|continuar|continue|confirmar|confirm)$/i]']
CONFIRMAR = re.compile(r"^(avançar|next|verificar|verify|continuar|continue|confirmar|confirm|enviar|send|entrar|log in)$", re.I)
ENVIAR_CODIGO = re.compile(r"^(enviar código|send code|obter código|get code)$", re.I)  # nunca "Reenviar": gasta tentativa
LIMITE = re.compile(r"máximo de tentativas|tente mais tarde|too many attempts|maximum number of attempts|try again later", re.I)

# Lê os clicáveis do modal de verificação (o elemento clicável mais externo de cada opção, com o texto e o centro na tela).
JS_OPCOES = r"""() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none' };
  const alvo = [...document.querySelectorAll('[role=dialog], [class*=modal i], [class*=Modal], [class*=verify i], [class*=Verify]')].filter(vis)
    .sort((a, b) => a.getBoundingClientRect().width * a.getBoundingClientRect().height - b.getBoundingClientRect().width * b.getBoundingClientRect().height)
    .find((e) => /verifi|confirm|identidade|identity/i.test(e.innerText || '')) || document.body;
  const clicavel = (e) => e.matches('button, a, [role=button], [role=option], [role=menuitem], li, [tabindex]') || getComputedStyle(e).cursor === 'pointer';
  const todos = [...alvo.querySelectorAll('*')].filter((e) => vis(e) && clicavel(e));
  const externos = todos.filter((e) => !todos.some((o) => o !== e && o.contains(e) && (o.innerText || '').trim() === (e.innerText || '').trim()) );
  const vistos = new Set(); const out = [];
  for (const e of externos) {
    const t = (e.innerText || e.getAttribute('aria-label') || '').trim().replace(/\s*\n\s*/g, ' · ').replace(/(\s*·)?\s*[›>»]\s*$/, '');
    if (!t || t.length > 80 || /^(feedback|ajuda|help|×|x|‹|<|voltar|back|fechar|close)/i.test(t)) continue;
    if ([...vistos].some((v) => v.includes(t) || t.includes(v))) continue;
    vistos.add(t); const r = e.getBoundingClientRect();
    out.push({ texto: t, x: r.left + r.width / 2, y: r.top + r.height / 2 });
  }
  return out;
}"""


def _verificacao(page) -> bool:
    try:
        return page.locator(TEXTO_VERIFICACAO).count() > 0
    except Exception:  # noqa: BLE001
        return False


def opcoes_da_tela(page) -> list[dict]:
    try:
        return page.evaluate(JS_OPCOES) or []
    except Exception:  # noqa: BLE001
        return []


JS_CLIQUE = """([x, y]) => { let e = document.elementFromPoint(x, y); const vistos = [];
  while (e && vistos.length < 6) { vistos.push(e); e.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
    e.dispatchEvent(new MouseEvent('mouseup', {bubbles: true})); e.click(); if (e.matches('button,a,[role=button],[tabindex]')) break; e = e.parentElement; }
  return vistos.length; }"""


def _assinatura(page) -> str:
    try:
        return page.evaluate("() => document.body.innerText.slice(0, 600)")
    except Exception:  # noqa: BLE001
        return ""


def _clicar(page, op: dict) -> None:
    """Clique de mouse de verdade; se a tela não mudar, dispara o clique direto no elemento (handlers do React)."""
    antes = _assinatura(page)
    guardar_falha(page, "tiktok-antes-clique")
    page.mouse.move(op["x"] - 30, op["y"] - 10)
    page.mouse.move(op["x"], op["y"], steps=8)
    page.mouse.click(op["x"], op["y"])
    time.sleep(2.5)
    if _assinatura(page) == antes:
        try:
            page.evaluate(JS_CLIQUE, [op["x"], op["y"]])
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2.5)
    guardar_falha(page, "tiktok-depois-clique")


def _resolver_verificacao(page, canal: Canal, estado: dict) -> None:
    """Verificação de identidade depois do QR, como um app faz: lê as opções reais do modal do TikTok (ex.: "Telefone · +55****1998",
    "E-mail · c***l@...") e mostra como botões na nossa tela; o toque da pessoa vira clique naquele elemento. Depois envia o código
    sozinho e pede o código na nossa tela. Só se não achar nada clicável cai no print com toque."""
    from app.redes.navegador import resolver_tela_com_a_pessoa
    try:
        corpo = page.evaluate("() => document.body.innerText")
    except Exception:  # noqa: BLE001
        corpo = ""
    if LIMITE.search(corpo or ""):
        guardar_falha(page, "tiktok-limite")
        raise ErroLogin("limite_codigos")
    cod = achar(page, CAMPO_CODIGO, 1)
    ops = opcoes_da_tela(page)
    if cod:
        envio = next((o for o in ops if ENVIAR_CODIGO.search(o["texto"])), None)
        if envio and not estado.get("codigo_enviado"):
            _clicar(page, envio)
            estado["codigo_enviado"] = True
            pausa(2, 3)
        v = canal.pedir(Passo("codigo_email", mensagem=f"O TikTok mandou um código {estado.get('via', '')} para confirmar que é você. Digite aqui.".replace("  ", " "),
                              campos=[{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]))
        digitar(cod, v.strip())
        pausa(0.6, 1)
        seguir = next((o for o in opcoes_da_tela(page) if CONFIRMAR.search(o["texto"]) and not ENVIAR_CODIGO.search(o["texto"])), None)
        if seguir:
            _clicar(page, seguir)
        else:
            page.keyboard.press("Enter")
        pausa(3, 4)
        return
    ops = [o for o in ops if not ENVIAR_CODIGO.search(o["texto"])] or ops
    if ops:
        esc = canal.pedir(Passo("escolha", mensagem="O TikTok quer confirmar que é você. Escolha por onde receber o código:", opcoes=[o["texto"] for o in ops]))
        op = next((o for o in ops if o["texto"] == esc), ops[0])
        estado["via"] = "por SMS" if re.search(r"telefone|phone|sms", op["texto"], re.I) else "por e-mail" if re.search(r"mail", op["texto"], re.I) else ""
        estado["codigo_enviado"] = False
        _clicar(page, op)
        pausa(2, 3)
        return
    guardar_falha(page, "tiktok-verificacao")
    resolver_tela_com_a_pessoa(page, canal, "O TikTok quer confirmar que é você. Toque na opção na imagem.")
    pausa(2.5, 3)


def login(canal: Canal, usuario: str = "", senha: str = "", proxy: str = "") -> tuple[dict, dict]:
    with abrir(proxy) as (ctx, page):
        page.goto("https://www.tiktok.com/login/qrcode", wait_until="domcontentloaded")
        fim = time.time() + 240
        ultimo = 0.0
        estado: dict = {}
        while time.time() < fim:
            if canal.cancelado():
                raise TimeoutError()
            if _logado(ctx):
                break
            if _verificacao(page):  # depois do QR o TikTok às vezes pede "confirme que é você"
                _resolver_verificacao(page, canal, estado)
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
