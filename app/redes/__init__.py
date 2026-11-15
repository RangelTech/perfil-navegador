"""Conectores por rede, mesma interface (spec 44 3.3.2):

    login(canal, usuario, senha, proxy) -> (sessao: dict, perfil: dict)
    ler_perfil(sessao, proxy) -> dict
    publicar(sessao, proxy, post) -> {"ok": True, "link": "..."}   post = {"tipo": "foto|video|carrossel|texto", "legenda": str, "arquivos": [caminhos]}
    aplicar(sessao, proxy, proposta) -> {"campo": "ok|falhou|so_pelo_app"}

Erros de sessão levantam ErroLogin("sessao_caiu"). O modo simulado (`simulado.py`) segue o mesmo contrato.
"""
from __future__ import annotations


def conector(rede: str, simulado: bool = False):
    if simulado:
        from app.redes import simulado as m
        return m
    if rede == "instagram":
        from app.redes import instagram_web as m  # instagrapi quebrou no login em 15/11/2026 (ver instagram_web.py)
    elif rede == "linkedin":
        from app.redes import linkedin as m
    elif rede == "facebook":
        from app.redes import facebook as m
    elif rede == "tiktok":
        from app.redes import tiktok as m
    else:
        raise ValueError("rede desconhecida")
    return m
