<!-- readme-padrao -->
# Perfil-navegador

> Serviço de perfis de navegador usados pelos produtos para logar nas redes sociais (pelo proxy de São Paulo).

![Página do repositório](docs/img/principal.webp)

## O que é
Serviço de perfis de navegador usados pelos produtos para logar nas redes sociais (pelo proxy de São Paulo).

Estado: **no ar**.

## Onde está no ar
- Sem endereço público próprio.

## Onde faz o deploy
Este repositório **só publica** o artefato (release com imagem e manifesto); **quem implanta é o `vps_rt_infra`**.

- Serviço `perfil-navegador`: `gh workflow run deploy.yml --repo RangelTech/vps_rt_infra -f service=perfil-navegador` (só validar: `-f dry_run=true`; voltar versão: `-f version=<tag-antiga>`)

Os `.env` desses serviços são gerados do Infisical no momento do deploy (spec 57, seção 0A).

## Como funciona por dentro
Resumo acima; os detalhes estão nas notas técnicas (README anterior) abaixo e na spec 57.

## Segredos
Nenhum valor de segredo fica neste repositório. Os segredos dos serviços ficam no Infisical (mapa em `vps_rt_infra/scripts/infisical/mapa_envs.json`) e chegam à VPS gerados no deploy.

## Rodar e testar localmente
Ver as notas técnicas abaixo (cada repositório tem o seu jeito); os testes de QA em produção são por cliques reais, com evidência em `new_ragente/qa/evidencias`.

## Links
- Repositório: https://github.com/RangelTech/perfil-navegador
- Painel único: https://painel.rangeltech.net
- Spec de organização geral: `new_ragente/specs/57_ORGANIZACAO_GERAL_PRODUTOS_E_PAINEL.md`

## Notas técnicas (README anterior)

# perfil-navegador

Serviço interno que entra nas redes **pelo servidor**, sempre pelo proxy SP (spec 44 3.3.2–3.3.4).
Atende a suíte de perfil (insta-ai, face-ai, tittok-ai, linkdn-ai) e o Posta AI. Só na rede interna da VPS, com token.

| Rede | Como entra | Publica |
|---|---|---|
| Instagram | API mobile (instagrapi): senha, 2FA, desafio "foi você?" | foto, Reels, carrossel; aplica nome/bio/link/foto |
| LinkedIn | Playwright: senha, código por e-mail/SMS, aprovar no app | texto com foto/vídeo |
| Facebook | Playwright: senha, código 2FA, aprovar no celular | texto com foto/vídeo no perfil |
| TikTok | Playwright: QR da página (lido no app) | vídeo pelo TikTok Studio |

- **Máquina de passos** (`app/passos.py`): cada login roda numa thread e devolve passos
  (`codigo_2fa`, `codigo_email`, `aprovar_no_celular`, `escolha`, `captcha`, `qr`, `conectado`, `erro`).
  Senha e códigos só na memória; nunca em disco nem em log.
- **Sessão cifrada** (`app/cofre.py`): Fernet com `PN_CHAVE`, em `/data/sessoes`. Sessão que cai é apagada (409).
- **Modo simulado** (`PN_SIMULADO=1`): mesmo contrato, sem rede (base dos testes).
- Falhas de tela ficam em `/data/falhas` (print) para ajustar seletor quando a rede muda o layout.

API: ver o topo de `app/main.py`. Variáveis: `PN_TOKEN`, `PN_CHAVE`, `PN_PROXY` (`http://usuario:senha@host:porta`), `PN_DADOS`.
Deploy: release neste repo (workflow `Release`), implantação só pelo `vps_rt_infra`.
