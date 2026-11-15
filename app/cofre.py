"""Sessões das contas (cookies do navegador ou settings do instagrapi), cifradas com Fernet no volume /data.

Sem a chave (PN_CHAVE) o serviço não guarda nada. A senha nunca chega aqui: só a sessão depois do login.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

RE_CONTA = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class Cofre:
    def __init__(self, pasta: str, chave: str):
        if not chave:
            raise RuntimeError("PN_CHAVE não configurada")
        self.f = Fernet(chave.encode())
        self.pasta = Path(pasta) / "sessoes"
        self.pasta.mkdir(parents=True, exist_ok=True)

    def _arq(self, conta: str) -> Path:
        if not RE_CONTA.match(conta or ""):
            raise ValueError("conta inválida")
        return self.pasta / (conta.replace(":", "_") + ".bin")

    def guardar(self, conta: str, rede: str, sessao: dict, perfil: dict | None = None) -> None:
        dados = json.dumps({"rede": rede, "sessao": sessao, "perfil": perfil or {}}).encode()
        tmp = self._arq(conta).with_suffix(".tmp")
        tmp.write_bytes(self.f.encrypt(dados))
        os.replace(tmp, self._arq(conta))

    def ler(self, conta: str) -> dict | None:
        a = self._arq(conta)
        if not a.exists():
            return None
        try:
            return json.loads(self.f.decrypt(a.read_bytes()))
        except InvalidToken:
            return None

    def apagar(self, conta: str) -> bool:
        a = self._arq(conta)
        if a.exists():
            a.unlink()
            return True
        return False
