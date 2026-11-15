"""Máquina de passos do login (igual à do gateway de canais do LUAR, spec 44 3.3.3).

Cada tentativa de login roda numa thread própria (o navegador/cliente fica vivo entre os passos).
A thread conversa com a API por duas filas: ela publica o passo atual e, quando precisa de algo da pessoa
(código, escolha), bloqueia esperando a resposta. Senha e códigos só passam pela memória; nada vai para log.
"""
from __future__ import annotations

import queue
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

PRAZO_PASSO_S = 5 * 60
VIDA_TENTATIVA_S = 10 * 60
TIPOS = {"credenciais", "codigo_2fa", "codigo_email", "aprovar_no_celular", "escolha", "captcha", "qr", "conectado", "erro"}


@dataclass
class Passo:
    tipo: str
    mensagem: str = ""
    campos: list[dict] = field(default_factory=list)     # [{"id": "codigo", "tipo": "texto|senha", "rotulo": "..."}]
    opcoes: list[str] = field(default_factory=list)      # escolha
    imagem: str = ""                                     # data:image/png;base64 (QR, captcha)
    erro: str = ""                                       # senha_errada | conta_bloqueada | prazo | rede_fora | desconhecido
    espera_s: int = 0                                    # aprovar_no_celular / qr: consultar de novo em N s

    def publico(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in ("", [], 0)}


class Cancelado(Exception):
    pass


class Canal:
    """Lado da thread de login: mostra um passo e (se preciso) espera a resposta."""

    def __init__(self, tentativa: "Tentativa"):
        self.t = tentativa

    def mostrar(self, p: Passo) -> None:
        self.t.publicar(p)

    def pedir(self, p: Passo, prazo: int = PRAZO_PASSO_S) -> str:
        self.t.publicar(p)
        try:
            v = self.t.respostas.get(timeout=prazo)
        except queue.Empty:
            raise TimeoutError("prazo do passo")
        if v is None:
            raise Cancelado()
        return v

    def cancelado(self) -> bool:
        return self.t.cancelada


class Tentativa:
    def __init__(self, rede: str, conta: str):
        self.id = secrets.token_urlsafe(16)
        self.rede, self.conta = rede, conta
        self.criada = time.time()
        self.passo: Passo | None = None
        self.versao = 0
        self.respostas: queue.Queue = queue.Queue()
        self.mudou = threading.Condition()
        self.cancelada = False
        self.sessao: dict | None = None
        self.perfil: dict | None = None

    def publicar(self, p: Passo) -> None:
        with self.mudou:
            self.passo = p
            self.versao += 1
            self.mudou.notify_all()

    def esperar_mudanca(self, versao: int, prazo: float) -> Passo | None:
        with self.mudou:
            self.mudou.wait_for(lambda: self.versao != versao, timeout=prazo)
            return self.passo

    def terminou(self) -> bool:
        return bool(self.passo and self.passo.tipo in ("conectado", "erro"))


class Gerente:
    """Guarda as tentativas vivas; `ao_conectar(tentativa)` grava a sessão cifrada."""

    def __init__(self, ao_conectar: Callable[[Tentativa], None]):
        self.tentativas: dict[str, Tentativa] = {}
        self.trava = threading.Lock()
        self.ao_conectar = ao_conectar

    def iniciar(self, rede: str, conta: str, login: Callable[[Canal], tuple[dict, dict]], espera: float = 60) -> Tentativa:
        self._limpar()
        t = Tentativa(rede, conta)
        with self.trava:
            self.tentativas[t.id] = t

        def rodar():
            canal = Canal(t)
            try:
                sessao, perfil = login(canal)
                t.sessao, t.perfil = sessao, perfil
                self.ao_conectar(t)
                t.publicar(Passo("conectado", mensagem="Conta conectada."))
            except Cancelado:
                t.publicar(Passo("erro", erro="cancelado", mensagem="Login cancelado."))
            except TimeoutError:
                t.publicar(Passo("erro", erro="prazo", mensagem="Demorou demais. Tente de novo."))
            except ErroLogin as e:
                t.publicar(Passo("erro", erro=e.codigo, mensagem=e.mensagem))
            except Exception:  # noqa: BLE001  (detalhe nunca vai para a pessoa nem com a senha)
                t.publicar(Passo("erro", erro="desconhecido", mensagem="A rede não deixou entrar agora. Tente de novo em alguns minutos."))

        threading.Thread(target=rodar, daemon=True, name=f"login-{rede}").start()
        t.esperar_mudanca(0, espera)
        return t

    def responder(self, tid: str, valor: str | None, espera: float = 60) -> Tentativa:
        t = self.pegar(tid)
        v = t.versao
        t.respostas.put(valor)
        if valor is None:
            t.cancelada = True
        t.esperar_mudanca(v, espera)
        return t

    def pegar(self, tid: str) -> Tentativa:
        t = self.tentativas.get(tid)
        if not t or time.time() - t.criada > VIDA_TENTATIVA_S:
            raise KeyError(tid)
        return t

    def _limpar(self) -> None:
        with self.trava:
            for k in [k for k, t in self.tentativas.items() if time.time() - t.criada > VIDA_TENTATIVA_S]:
                t = self.tentativas.pop(k)
                if not t.terminou():
                    t.cancelada = True
                    t.respostas.put(None)


class ErroLogin(Exception):
    MENSAGENS = {"senha_errada": "Usuário ou senha errados.", "conta_bloqueada": "A rede bloqueou a conta por segurança. Entre pelo app e libere.",
                 "codigo_errado": "Código errado.", "rede_fora": "A rede não respondeu. Tente de novo em instantes.",
                 "captcha": "A rede pediu um desafio que não dá para resolver por aqui. Tente mais tarde.",
                 "sessao_caiu": "A rede derrubou a sessão. Conecte de novo."}

    def __init__(self, codigo: str, mensagem: str = ""):
        super().__init__(codigo)
        self.codigo = codigo
        self.mensagem = mensagem or self.MENSAGENS.get(codigo, "Não deu para entrar.")
