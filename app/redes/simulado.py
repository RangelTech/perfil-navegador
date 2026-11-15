"""Conector simulado: mesmas respostas das redes reais, sem rede. Usuário define o caminho:

- "erro"      -> senha errada
- "2fa"       -> pede código de 2 fatores (certo: 123456)
- "celular"   -> aprovar no celular (aprova na 2ª consulta)
- "escolha"   -> pergunta por onde receber o código, depois código por e-mail
- qualquer outro -> conecta direto
"""
from __future__ import annotations

import time

from app.passos import Canal, ErroLogin, Passo

PUBLICADOS: list[dict] = []


def login(canal: Canal, usuario: str, senha: str, proxy: str = "") -> tuple[dict, dict]:
    if usuario == "erro" or not senha:
        raise ErroLogin("senha_errada")
    if usuario == "2fa":
        for _ in range(3):
            c = canal.pedir(Passo("codigo_2fa", mensagem="Digite o código do app autenticador ou do SMS.", campos=[{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]))
            if c.strip() == "123456":
                break
            canal.mostrar(Passo("codigo_2fa", erro="codigo_errado", mensagem="Código errado."))
        else:
            raise ErroLogin("codigo_errado")
    elif usuario == "celular":
        canal.mostrar(Passo("aprovar_no_celular", mensagem="Abra o app e toque em 'Sou eu'.", espera_s=1))
        time.sleep(0.3)
    elif usuario == "escolha":
        via = canal.pedir(Passo("escolha", mensagem="Por onde quer receber o código?", opcoes=["SMS", "E-mail"]))
        c = canal.pedir(Passo("codigo_email", mensagem=f"Mandamos um código por {via}.", campos=[{"id": "codigo", "tipo": "texto", "rotulo": "Código"}]))
        if c.strip() != "654321":
            raise ErroLogin("codigo_errado")
    return {"cookies": [{"name": "sessionid", "value": "sim-" + usuario}]}, {"usuario": usuario, "nome": "Conta Simulada", "bio": "", "seguidores": 1234}


def ler_perfil(sessao: dict, proxy: str = "") -> dict:
    if not sessao.get("cookies"):
        raise ErroLogin("sessao_caiu")
    return {"usuario": sessao["cookies"][0]["value"][4:], "nome": "Conta Simulada", "bio": "Bio simulada", "seguidores": 1234, "posts": 10}


def publicar(sessao: dict, proxy: str, post: dict) -> dict:
    if not sessao.get("cookies"):
        raise ErroLogin("sessao_caiu")
    PUBLICADOS.append(post)
    return {"ok": True, "link": f"https://sim.local/p/{len(PUBLICADOS)}"}


def aplicar(sessao: dict, proxy: str, proposta: dict) -> dict:
    return {k: "ok" for k in proposta}
