"""perfil-navegador: serviço interno que entra nas redes pelo servidor (spec 44 3.3.2-3.3.4).

Usado pela suíte de perfil (insta-ai, face-ai, tittok-ai, linkdn-ai) e pelo Posta AI. Só na rede interna da VPS,
com token (PN_TOKEN). Cada produto identifica a conta como "<produto>:<id>" e nunca vê a sessão.

POST   /logins                       {rede, conta, usuario, senha}  -> {id, passo}
GET    /logins/{id}                                                  -> {id, passo}   (consulta: QR novo, aprovar no celular)
POST   /logins/{id}/responder        {valor}                         -> {id, passo}
POST   /logins/{id}/cancelar
GET    /contas/{conta}                                               -> {conectada, rede, perfil}
POST   /contas/{conta}/perfil                                        -> perfil lido agora
POST   /contas/{conta}/publicar      {tipo, legenda, arquivos:[{nome, base64}]} -> {ok, link}
POST   /contas/{conta}/aplicar       {campo: valor}                  -> {campo: ok|falhou|so_pelo_app}
DELETE /contas/{conta}                                               -> apaga a sessão
"""
from __future__ import annotations

import base64
import hmac
import logging
import os
import re
import shutil
import tempfile
import threading

from fastapi import FastAPI, HTTPException, Request

from app.cofre import RE_CONTA, Cofre
from app.passos import ErroLogin, Gerente, Tentativa
from app.redes import conector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("perfil-navegador")
REDES = {"instagram", "linkedin", "facebook", "tiktok"}
EXT_OK = re.compile(r"\.(jpg|jpeg|png|webp|mp4|mov)$", re.I)
LIMITE_ARQUIVO = 300 * 1024 * 1024


def criar_app(dados: str | None = None, token: str | None = None, chave: str | None = None, simulado: bool | None = None,
              proxy: str | None = None) -> FastAPI:
    dados = dados or os.environ.get("PN_DADOS", "/data")
    token = token if token is not None else os.environ.get("PN_TOKEN", "")
    simulado = simulado if simulado is not None else os.environ.get("PN_SIMULADO") == "1"
    proxy = proxy if proxy is not None else os.environ.get("PN_PROXY", "")
    cofre = Cofre(dados, chave if chave is not None else os.environ.get("PN_CHAVE", ""))
    ger = Gerente(lambda t: cofre.guardar(t.conta, t.rede, t.sessao or {}, t.perfil))
    trava_conta: dict[str, threading.Lock] = {}
    app = FastAPI(title="perfil-navegador", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def autentica(request: Request, call_next):
        if request.url.path != "/health":
            esquema, _, tok = request.headers.get("authorization", "").partition(" ")
            if not token or esquema.lower() != "bearer" or not hmac.compare_digest(tok, token):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "não autorizado"}, status_code=401)
        return await call_next(request)

    def vista(t: Tentativa) -> dict:
        return {"id": t.id, "rede": t.rede, "conta": t.conta, "passo": t.passo.publico() if t.passo else {"tipo": "credenciais"}}

    def conta_ok(conta: str) -> str:
        if not RE_CONTA.match(conta or ""):
            raise HTTPException(422, "conta inválida")
        return conta

    def trava(conta: str) -> threading.Lock:
        return trava_conta.setdefault(conta, threading.Lock())

    @app.get("/health")
    def health():
        return {"ok": True, "simulado": simulado}

    @app.post("/logins")
    async def logins(request: Request):
        b = await request.json()
        rede, conta = b.get("rede"), conta_ok(str(b.get("conta") or ""))
        if rede not in REDES:
            raise HTTPException(422, "rede desconhecida")
        usuario, senha = str(b.get("usuario") or "").strip(), str(b.get("senha") or "")
        if rede != "tiktok" and (not usuario or not senha):
            raise HTTPException(422, "informe usuário e senha")
        mod = conector(rede, simulado)
        t = ger.iniciar(rede, conta, lambda canal: mod.login(canal, usuario, senha, proxy), espera=0.5 if simulado else 60)
        del senha
        return vista(t)

    def pegar(tid: str) -> Tentativa:
        try:
            return ger.pegar(tid)
        except KeyError:
            raise HTTPException(404, "tentativa expirada; comece de novo")

    @app.get("/logins/{tid}")
    def login_status(tid: str):
        return vista(pegar(tid))

    @app.post("/logins/{tid}/responder")
    async def responder(tid: str, request: Request):
        pegar(tid)
        v = str((await request.json()).get("valor") or "")[:200]
        return vista(ger.responder(tid, v, espera=0.5 if simulado else 60))

    @app.post("/logins/{tid}/cancelar")
    def cancelar(tid: str):
        pegar(tid)
        return vista(ger.responder(tid, None, espera=5))

    @app.get("/contas/{conta}")
    def conta_get(conta: str):
        s = cofre.ler(conta_ok(conta))
        return {"conectada": bool(s), "rede": s["rede"] if s else None, "perfil": s["perfil"] if s else None}

    def com_sessao(conta: str, fn):
        s = cofre.ler(conta_ok(conta))
        if not s:
            raise HTTPException(409, "conta não conectada")
        mod = conector(s["rede"], simulado)
        with trava(conta):
            try:
                return fn(mod, s)
            except ErroLogin as e:
                if e.codigo == "sessao_caiu":
                    cofre.apagar(conta)
                    raise HTTPException(409, e.mensagem)
                raise HTTPException(422, e.mensagem)
            except ValueError as e:
                raise HTTPException(422, str(e))
            except Exception as e:  # noqa: BLE001
                log.warning("falha em %s (%s): %s", conta, s["rede"], type(e).__name__)
                raise HTTPException(502, "a rede não respondeu como esperado; tente de novo")

    @app.post("/contas/{conta}/perfil")
    def perfil(conta: str):
        def f(mod, s):
            p = mod.ler_perfil(s["sessao"], proxy)
            cofre.guardar(conta, s["rede"], s["sessao"], p)
            return p
        return com_sessao(conta, f)

    @app.post("/contas/{conta}/publicar")
    async def publicar(conta: str, request: Request):
        b = await request.json()
        tipo = b.get("tipo")
        if tipo not in ("foto", "video", "carrossel", "texto"):
            raise HTTPException(422, "tipo inválido")
        pasta = tempfile.mkdtemp(prefix="pn-")
        try:
            arqs = []
            for i, a in enumerate((b.get("arquivos") or [])[:10]):
                nome = os.path.basename(str(a.get("nome") or f"arquivo{i}.jpg"))
                if not EXT_OK.search(nome):
                    raise HTTPException(422, f"formato não aceito: {nome}")
                dados_arq = base64.b64decode(a.get("base64") or "", validate=False)
                if not dados_arq or len(dados_arq) > LIMITE_ARQUIVO:
                    raise HTTPException(422, "arquivo vazio ou grande demais")
                caminho = os.path.join(pasta, f"{i}-{nome}")
                with open(caminho, "wb") as f:
                    f.write(dados_arq)
                arqs.append(caminho)
            post = {"tipo": tipo, "legenda": str(b.get("legenda") or "")[:5000], "arquivos": arqs}
            return com_sessao(conta, lambda mod, s: mod.publicar(s["sessao"], proxy, post))
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

    @app.post("/contas/{conta}/aplicar")
    async def aplicar(conta: str, request: Request):
        proposta = {k: v for k, v in (await request.json()).items() if isinstance(v, str)}
        return com_sessao(conta, lambda mod, s: mod.aplicar(s["sessao"], proxy, proposta))

    @app.delete("/contas/{conta}")
    def apagar(conta: str):
        return {"apagada": cofre.apagar(conta_ok(conta))}

    return app


app = criar_app() if os.environ.get("PN_SEM_APP") != "1" else None
