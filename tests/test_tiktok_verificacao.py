"""Verificação do TikTok depois do QR: lê as opções do modal, a escolha vira clique, envia o código e digita o que a pessoa mandou."""
import pytest

pw = pytest.importorskip("playwright.sync_api")
from app.passos import Passo
from app.redes import tiktok

HTML = """<html><body style="background:#111;color:#fff;font-family:sans-serif">
<h2>Entrar com código QR</h2>
<div class="TUXModal" style="width:420px;margin:40px auto;border:1px solid red;padding:20px">
  <div style="cursor:pointer">‹</div><div style="cursor:pointer">×</div>
  <h3>Verifique se é realmente você</h3><p>Antes de continuar, verifique sua identidade usando um dos seguintes métodos a seguir.</p>
  <div id="lista">
    <div class="item" style="cursor:pointer;padding:12px" onclick="metodo('sms')"><div><span>Telefone</span><br><small>+55****1998</small></div><span>›</span></div>
    <div class="item" style="cursor:pointer;padding:12px" onclick="metodo('email')"><div><span>E-mail</span><br><small>c***l@rangeltech.net</small></div><span>›</span></div>
  </div>
</div>
<script>
function metodo(m){ window.escolhido=m; document.getElementById('lista').innerHTML =
  '<input placeholder="Digite o código de 6 dígitos" maxlength="6" id="c"><button onclick="window.enviado=true">Enviar código</button><button onclick="window.final=c.value">Avançar</button>'; }
</script></body></html>"""


class CanalFake:
    def __init__(self, respostas):
        self.respostas, self.vistos = list(respostas), []
    def pedir(self, p: Passo, prazo=0):
        self.vistos.append(p); return self.respostas.pop(0)
    def mostrar(self, p): self.vistos.append(p)
    def cancelado(self): return False


def test_verificacao_telefone_ate_codigo(monkeypatch):
    monkeypatch.setattr(tiktok, "pausa", lambda *a, **k: None)
    with pw.sync_playwright() as p:
        b = p.chromium.launch(); page = b.new_page(); page.set_content(HTML)
        assert tiktok._verificacao(page)
        ops = tiktok.opcoes_da_tela(page)
        textos = [o["texto"] for o in ops]
        assert any(t.startswith("Telefone") and "1998" in t for t in textos), textos
        assert any(t.startswith("E-mail") for t in textos), textos
        assert not any(t in ("‹", "×") for t in textos)
        canal, estado = CanalFake([next(t for t in textos if t.startswith("Telefone")), "123456"]), {}
        tiktok._resolver_verificacao(page, canal, estado)
        assert page.evaluate("window.escolhido") == "sms"
        tiktok._resolver_verificacao(page, canal, estado)
        assert page.evaluate("window.enviado") is True
        assert page.evaluate("window.final") == "123456"
        assert canal.vistos[0].tipo == "escolha" and canal.vistos[1].tipo == "codigo_email" and "SMS" in canal.vistos[1].mensagem
        b.close()
