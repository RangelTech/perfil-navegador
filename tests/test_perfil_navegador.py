"""Serviço perfil-navegador em modo simulado: passos de login, sessão cifrada, publicar, autenticação."""
import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PN_SEM_APP"] = "1"

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import criar_app  # noqa: E402
from app.redes import simulado  # noqa: E402

H = {"Authorization": "Bearer tk"}


@pytest.fixture
def c(tmp_path):
    app = criar_app(dados=str(tmp_path), token="tk", chave=Fernet.generate_key().decode(), simulado=True, proxy="")
    return TestClient(app), tmp_path


def esperar(cl, tid, tipo, n=20):
    import time
    for _ in range(n):
        r = cl.get(f"/logins/{tid}", headers=H).json()
        if r["passo"]["tipo"] == tipo:
            return r
        time.sleep(0.1)
    return r


def test_sem_token_401(c):
    cl, _ = c
    assert cl.post("/logins", json={}).status_code == 401
    assert cl.post("/logins", json={}, headers={"Authorization": "Bearer x"}).status_code == 401
    assert cl.get("/health").status_code == 200


def test_login_direto_guarda_sessao_cifrada(c):
    cl, pasta = c
    r = cl.post("/logins", json={"rede": "instagram", "conta": "perfilai:1", "usuario": "ana", "senha": "s3nha-secreta"}, headers=H).json()
    r = esperar(cl, r["id"], "conectado")
    assert r["passo"]["tipo"] == "conectado"
    bruto = b"".join(p.read_bytes() for p in (pasta / "sessoes").iterdir())
    assert b"s3nha" not in bruto and b"sim-ana" not in bruto  # cifrado e sem senha
    g = cl.get("/contas/perfilai:1", headers=H).json()
    assert g["conectada"] and g["rede"] == "instagram" and g["perfil"]["usuario"] == "ana"


def test_senha_errada(c):
    cl, _ = c
    r = cl.post("/logins", json={"rede": "linkedin", "conta": "x:1", "usuario": "erro", "senha": "s"}, headers=H).json()
    r = esperar(cl, r["id"], "erro")
    assert r["passo"]["erro"] == "senha_errada"
    assert not cl.get("/contas/x:1", headers=H).json()["conectada"]


def test_2fa_com_codigo_errado_e_certo(c):
    cl, _ = c
    r = cl.post("/logins", json={"rede": "facebook", "conta": "x:2", "usuario": "2fa", "senha": "s"}, headers=H).json()
    r = esperar(cl, r["id"], "codigo_2fa")
    assert r["passo"]["campos"][0]["id"] == "codigo"
    r = cl.post(f"/logins/{r['id']}/responder", json={"valor": "000000"}, headers=H).json()
    assert r["passo"]["tipo"] == "codigo_2fa"
    r = cl.post(f"/logins/{r['id']}/responder", json={"valor": "123456"}, headers=H).json()
    r = esperar(cl, r["id"], "conectado")
    assert r["passo"]["tipo"] == "conectado"


def test_escolha_e_codigo_email(c):
    cl, _ = c
    r = cl.post("/logins", json={"rede": "instagram", "conta": "x:3", "usuario": "escolha", "senha": "s"}, headers=H).json()
    r = esperar(cl, r["id"], "escolha")
    assert r["passo"]["opcoes"] == ["SMS", "E-mail"]
    r = cl.post(f"/logins/{r['id']}/responder", json={"valor": "E-mail"}, headers=H).json()
    r = esperar(cl, r["id"], "codigo_email")
    r = cl.post(f"/logins/{r['id']}/responder", json={"valor": "654321"}, headers=H).json()
    assert esperar(cl, r["id"], "conectado")["passo"]["tipo"] == "conectado"


def test_cancelar(c):
    cl, _ = c
    r = cl.post("/logins", json={"rede": "facebook", "conta": "x:4", "usuario": "2fa", "senha": "s"}, headers=H).json()
    esperar(cl, r["id"], "codigo_2fa")
    r = cl.post(f"/logins/{r['id']}/cancelar", headers=H).json()
    assert r["passo"]["tipo"] == "erro" and r["passo"]["erro"] == "cancelado"


def test_publicar_e_desconectar(c):
    cl, _ = c
    r = cl.post("/logins", json={"rede": "instagram", "conta": "posta:9", "usuario": "loja", "senha": "s"}, headers=H).json()
    esperar(cl, r["id"], "conectado")
    foto = base64.b64encode(b"\xff\xd8fakejpeg").decode()
    p = cl.post("/contas/posta:9/publicar", json={"tipo": "foto", "legenda": "Promo de sexta", "arquivos": [{"nome": "a.jpg", "base64": foto}]}, headers=H).json()
    assert p["ok"] and p["link"].startswith("https://sim.local/p/")
    assert simulado.PUBLICADOS[-1]["legenda"] == "Promo de sexta"
    assert cl.post("/contas/posta:9/publicar", json={"tipo": "foto", "arquivos": [{"nome": "a.exe", "base64": foto}]}, headers=H).status_code == 422
    assert cl.post("/contas/posta:9/aplicar", json={"bio": "nova"}, headers=H).json() == {"bio": "ok"}
    assert cl.delete("/contas/posta:9", headers=H).json()["apagada"]
    assert cl.post("/contas/posta:9/publicar", json={"tipo": "foto", "arquivos": []}, headers=H).status_code == 409


def test_conta_invalida(c):
    cl, _ = c
    assert cl.get("/contas/..%2Fetc", headers=H).status_code in (404, 422)
    assert cl.post("/logins", json={"rede": "orkut", "conta": "x:1", "usuario": "a", "senha": "b"}, headers=H).status_code == 422
