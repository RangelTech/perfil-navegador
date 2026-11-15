"""Instagram pela API mobile (instagrapi), sempre pelo proxy SP.

Login: senha -> (2FA por app/SMS) -> (desafio "foi você?" com código por e-mail/SMS) -> sessão = settings do instagrapi.
O desafio do instagrapi chama `challenge_code_handler` de forma síncrona; aqui ele vira um passo e a thread espera a resposta.
"""
from __future__ import annotations

from app.passos import Canal, ErroLogin, Passo

CAMPO_CODIGO = [{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]


def _cliente(proxy: str, settings: dict | None = None):
    from instagrapi import Client
    cl = Client(settings or {})
    cl.delay_range = [1, 3]
    if proxy:
        cl.set_proxy(proxy)
    cl.set_locale("pt_BR")
    cl.set_country("BR")
    cl.set_country_code(55)
    cl.set_timezone_offset(-3 * 3600)
    return cl


def _perfil(cl) -> dict:
    a = cl.account_info()
    try:
        u = cl.user_info_by_username(a.username)
        seguidores, posts = u.follower_count, u.media_count
    except Exception:  # noqa: BLE001
        seguidores = posts = None
    return {"usuario": a.username, "nome": a.full_name, "bio": a.biography, "link": str(a.external_url or ""),
            "foto": str(a.profile_pic_url or ""), "seguidores": seguidores, "posts": posts}


def login(canal: Canal, usuario: str, senha: str, proxy: str = "") -> tuple[dict, dict]:
    from instagrapi.exceptions import (BadPassword, ChallengeRequired, PleaseWaitFewMinutes, RecaptchaChallengeForm,
                                       TwoFactorRequired, UserNotFound)
    from instagrapi.mixins.challenge import ChallengeChoice

    cl = _cliente(proxy)

    def codigo_desafio(_username, escolha):
        via = "e-mail" if escolha == ChallengeChoice.EMAIL else "SMS"
        return canal.pedir(Passo("codigo_email", mensagem=f"O Instagram mandou um código por {via} para confirmar que é você.", campos=CAMPO_CODIGO)).strip()

    cl.challenge_code_handler = codigo_desafio
    try:
        try:
            cl.login(usuario, senha)
        except TwoFactorRequired:
            for tentativa in range(3):
                cod = canal.pedir(Passo("codigo_2fa", mensagem="Digite o código do app autenticador ou do SMS do Instagram.", campos=CAMPO_CODIGO,
                                        erro="codigo_errado" if tentativa else "")).strip()
                try:
                    cl.login(usuario, senha, verification_code=cod)
                    break
                except (BadPassword, TwoFactorRequired):
                    continue
            else:
                raise ErroLogin("codigo_errado")
    except (BadPassword, UserNotFound):
        raise ErroLogin("senha_errada")
    except RecaptchaChallengeForm:
        raise ErroLogin("captcha")
    except PleaseWaitFewMinutes:
        raise ErroLogin("rede_fora", "O Instagram pediu para esperar alguns minutos antes de tentar de novo.")
    except ChallengeRequired:
        raise ErroLogin("conta_bloqueada", "O Instagram pediu uma confirmação no app. Abra o Instagram, confirme que foi você e tente de novo.")
    return cl.get_settings(), _perfil(cl)


def _com_sessao(sessao: dict, proxy: str):
    from instagrapi.exceptions import LoginRequired
    cl = _cliente(proxy, sessao)
    try:
        cl.get_timeline_feed()
    except LoginRequired:
        raise ErroLogin("sessao_caiu")
    return cl


def ler_perfil(sessao: dict, proxy: str = "") -> dict:
    return _perfil(_com_sessao(sessao, proxy))


def publicar(sessao: dict, proxy: str, post: dict) -> dict:
    cl = _com_sessao(sessao, proxy)
    arqs, legenda, tipo = post.get("arquivos") or [], post.get("legenda") or "", post.get("tipo")
    if tipo == "carrossel" and len(arqs) >= 2:
        m = cl.album_upload(arqs[:10], legenda)
    elif tipo == "video":
        m = cl.clip_upload(arqs[0], legenda)  # Reels
    elif tipo == "foto" and arqs:
        m = cl.photo_upload(arqs[0], legenda)
    else:
        raise ValueError("o Instagram precisa de foto ou vídeo")
    return {"ok": True, "link": f"https://www.instagram.com/p/{m.code}/"}


def aplicar(sessao: dict, proxy: str, proposta: dict) -> dict:
    """Campos da suíte de perfil: nome, bio, link. Foto de perfil por arquivo."""
    cl = _com_sessao(sessao, proxy)
    out = {}
    campos = {k: proposta[k] for k in ("nome", "bio", "link") if k in proposta}
    if campos:
        try:
            cl.account_edit(**{{"nome": "full_name", "bio": "biography", "link": "external_url"}[k]: v for k, v in campos.items()})
            out.update({k: "ok" for k in campos})
        except Exception:  # noqa: BLE001
            out.update({k: "falhou" for k in campos})
    if proposta.get("foto"):
        try:
            cl.account_change_picture(proposta["foto"])
            out["foto"] = "ok"
        except Exception:  # noqa: BLE001
            out["foto"] = "falhou"
    for k in proposta:
        out.setdefault(k, "so_pelo_app")
    return out
