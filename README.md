# ⚽ Bolão Copa 2026

Aplicação web minimalista para organizar um bolão privado da Copa do Mundo FIFA 2026 entre amigos, família ou colegas. Construída com FastAPI + SQLite no backend e HTML/CSS/JS puro (sem frameworks) no frontend — fácil de hospedar em qualquer VPS com Docker.

## Funcionalidades

- Cadastro com aprovação manual pelo administrador
- Email único por conta
- Palpites bloqueados automaticamente 1 hora antes de cada jogo
- Filtros: todos os jogos, jogos do Brasil, ou por grupo (A-L)
- Pontuação: 4 pontos por placar exato, 0 para qualquer outro resultado
- Ranking geral com desempate por acertos exatos
- Valores configuráveis por categoria (Brasil vs fase de grupos), apenas para exibição
- Recibo por email via Gmail SMTP
- Painel admin: aprovação de usuários, papéis, inserção de resultados
- Modal de boas-vindas no primeiro acesso + botão de regras
- Layout responsivo para celular
- Bandeiras das seleções via flagcdn.com com fallback local em SVG

## Stack

- Backend: Python 3.12, FastAPI, SQLite
- Frontend: HTML + CSS + JavaScript vanilla (arquivo único)
- Autenticação: cookie HTTP-only, senha com PBKDF2-SHA256
- Email: Gmail SMTP (opcional)
- Deploy: Docker + Docker Compose

## Como rodar

Pré-requisitos: Docker e Docker Compose instalados.

1. Clone o repositório e entre na pasta:

       git clone https://github.com/tiagochavo87/bolao-copa-2026.git
       cd bolao-copa-2026

2. Copie o arquivo de exemplo de variáveis de ambiente:

       cp .env.example .env

3. Edite o `.env` com suas configurações.

4. Suba a aplicação:

       docker compose up -d --build

5. Acesse http://localhost:8000

Por padrão o `docker-compose.yml` expõe a porta apenas em 127.0.0.1. Para acesso externo direto, troque para `0.0.0.0:8000:8000` — mas o recomendado é usar um proxy reverso (Nginx, Caddy, Traefik) com HTTPS.

## Configuração

Variáveis de ambiente no arquivo `.env`:

| Variável | Obrigatório | Descrição |
| --- | --- | --- |
| BOLAO_SECRET | Sim | String aleatória longa |
| ADMIN_USER | Sim | Usuário do administrador |
| ADMIN_PASS | Sim | Senha do administrador |
| GMAIL_USER | Não | Email Gmail para recibos |
| GMAIL_APP | Não | Senha de app do Gmail |
| PRECO_BRASIL | Não | Valor (R$) por palpite em jogos do Brasil. Padrão: 5 |
| PRECO_GRUPOS | Não | Valor (R$) por palpite na fase de grupos. Padrão: 10 |

Contas Google gerenciadas por organizações costumam bloquear "senhas de app". Use uma conta @gmail.com pessoal com verificação em duas etapas ativada. Sem isso, o app funciona normalmente, só o recibo por email fica indisponível.

## Fluxo de uso

1. Administrador faz login com ADMIN_USER / ADMIN_PASS.
2. Participantes se cadastram (usuário + email + senha).
3. Administrador aprova cada cadastro na aba Admin.
4. Participantes fazem palpites na aba Palpites.
5. Palpites bloqueados 1 hora antes de cada jogo.
6. Administrador insere resultados direto no card da partida.
7. Ranking recalculado automaticamente, 4 pontos por placar exato.
8. Cada participante vê o valor total a pagar e pode receber recibo por email.

## Pontuação

| Resultado | Pontos |
| --- | --- |
| Placar exato | 4 |
| Qualquer outro | 0 |

Desempate por número de acertos exatos.

## Sobre os valores

Os valores exibidos são apenas informativos, o sistema não processa pagamentos. O acerto de contas é feito fora da aplicação (Pix, dinheiro etc).

## Estrutura

- main.py
- index.html
- requirements.txt
- Dockerfile
- docker-compose.yml
- .env.example
- flags/

## Segurança

- Senhas com PBKDF2-SHA256 (260.000 iterações) + salt por usuário
- Sessões via cookie httponly + samesite=lax
- Nenhuma credencial hardcoded, tudo via variáveis de ambiente
- Banco SQLite em volume Docker persistente

## Dados da Copa 2026

Os 48 jogos da fase de grupos (12 grupos de 4 seleções) já vêm pré-carregados no banco, baseados na tabela oficial da FIFA. Horários em UTC.

## Licença

MIT
