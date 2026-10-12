# focomob-instagram-bot

Publica no Instagram da Focomob os itens de `queue.json` (Reels, foto única ou carrossel) na data/hora marcada,
via GitHub Actions (confere a cada 15 minutos). Mesmo padrão do robô do Seu Zé, mas **com marca separada**
(nada da Focomob no repositório do Seu Zé e vice-versa) e com suporte a **Reels**.

## Como funciona
- `queue.json`: lista de itens `{id, date (ISO, com fuso), type: reel|image|carousel, media, caption}`.
- `poster.py`: para cada item vencido e ainda não publicado, cria o container na API do Instagram, espera o vídeo
  ficar pronto (status FINISHED) e publica. Estado em `state.json`. Se algo falhar, o job fica **vermelho**.
- `refresh_token.py` (segundas, 03h de Fortaleza): renova o token (~60 dias) e grava no secret `IG_ACCESS_TOKEN`.
- As mídias ficam em `media/` e a Meta as baixa de `raw.githubusercontent.com` — por isso o repositório precisa ser **público**.

## O que só o José pode fazer (login/tokens — o Claude não digita senha nem token)
1. **Conta do Instagram da Focomob**: tem que ser *Profissional* (Comercial ou Criador). Em Configurações > Tipo de conta.
2. **App da Meta** (developers.facebook.com): usar o app "Automação Seu Zé" ou criar um novo ("Automação Focomob"),
   com o produto *Instagram API com Instagram Login*.
   - Funções do app > Funções > **Testadores do Instagram** > adicionar o @ da Focomob.
   - No Instagram da Focomob: Configurações > Apps e sites > **Convites de testador** > aceitar.
   - No app > Instagram > Configuração da API > **Gerar token** da conta da Focomob. Anotar o token e o **ID da conta** (IG_USER_ID).
3. **Secrets do repositório** (Settings > Secrets and variables > Actions) — pelo terminal, na pasta do projeto:
   ```
   gh secret set IG_USER_ID
   gh secret set IG_ACCESS_TOKEN
   gh secret set GH_PAT
   ```
   (`GH_PAT` = token fine-grained do GitHub só deste repositório, com permissão *Secrets: Read and write*; é ele que permite
   ao robô renovar o token do Instagram sozinho.)

## Publicar algo novo
Acrescentar um item em `queue.json` (e a mídia em `media/`), fazer commit e push. Para publicar na hora, rodar o workflow
manualmente (aba Actions > "Publicar no Instagram da Focomob" > Run workflow).

Teste sem publicar nada: `DRY_RUN=1 python poster.py`.
