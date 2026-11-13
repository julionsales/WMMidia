# Monitor Automotivo

Plataforma web para acompanhar empresas do setor automotivo: **estoque de veículos** coletado dos
sites das lojas + **presença pública no Instagram**, com dashboards, comparativos e **briefings de
marketing** versionados (DOCX) para reuniões com clientes.

Evolução do projeto `azul_premium_scraper` — veja [legacy/azul_premium_scraper/ANALISE.md](legacy/azul_premium_scraper/ANALISE.md)
para o que foi encontrado, corrigido e reaproveitado.

## Sumário
1. [Arquitetura](#arquitetura)
2. [Início rápido](#início-rápido)
3. [Configuração do ambiente](#configuração-do-ambiente)
4. [Primeiro administrador](#primeiro-administrador)
5. [Cadastro de empresas](#cadastro-de-empresas)
6. [Coletas e agendamento](#coletas-e-agendamento)
7. [Sessão de consulta do Instagram (opcional)](#sessão-de-consulta-do-instagram-opcional)
8. [Indicadores e regras](#indicadores-e-regras)
9. [Logs](#logs)
10. [Exportações e briefings](#exportações-e-briefings)
11. [Backup e restauração do MongoDB](#backup-e-restauração-do-mongodb)
12. [Dados demonstrativos](#dados-demonstrativos)
13. [Testes e validação](#testes-e-validação)
14. [Modelo de dados](#modelo-de-dados)
15. [Limitações conhecidas](#limitações-conhecidas)

## Arquitetura

```
navegador ──► frontend (nginx + Vue 3) ──/api──► api (FastAPI)
                                                  │  registra execução + enfileira
                                                  ▼
             scheduler (Celery Beat) ──► redis (fila/locks) ──► worker (Celery + Playwright + Instaloader)
                                                  │                         │
                                                  └──────► mongodb ◄────────┘  (dados de negócio e históricos)
```

| Serviço | Papel | Porta pública |
|---|---|---|
| `frontend` | SPA Vue 3 + Vite + PrimeVue + ECharts servida por nginx; proxy de `/api` | **sim** (`127.0.0.1:8080` por padrão) |
| `api` | FastAPI + Pydantic; nunca faz coleta, só registra e enfileira | não |
| `worker` | Celery: coleta de estoque (requests/Playwright) e Instagram | não (tem saída para internet) |
| `scheduler` | Celery Beat — **uma única instância** | não |
| `init` | Etapa explícita de migrações/índices (roda e termina) | não |
| `mongo` | MongoDB 8 com autenticação | não (rede interna) |
| `redis` | Broker Celery, locks e controle de taxa, com senha | não (rede interna) |

Estrutura do código:

```
backend/app/
  core/          configuração, segurança (Argon2 + JWT), logs com remoção de segredos, validação de URLs (SSRF), datas
  db/            clientes MongoDB (PyMongo assíncrono) e migrações versionadas
  models/        schemas Pydantic e serialização (ObjectId -> str, datas UTC ISO-8601)
  services/
    inventory/   fetchers seguros, parsers por site (azul, hazul, avance, generic, playwright), normalização, persistência
    instagram/   provedores (Instaloader; stub para API oficial) e persistência de snapshots/posts/métricas
    metrics/     indicadores do Instagram e do estoque, painéis e comparativos
    briefing/    regras transparentes, montagem versionada e DOCX
    runs.py      ciclo de vida das execuções (idempotência, leases)
  api/           rotas FastAPI
  worker/        app Celery, tarefas e agendador
  cli/           migrate, create_admin, seed_demo
backend/tests/   testes com fixtures (sem acesso externo)
frontend/src/    views, componentes, stores Pinia, roteador
```

**Async × Celery.** API e worker compartilham os mesmos serviços assíncronos. Na API há um
`AsyncMongoClient` por processo (lifespan). No worker cada acesso ao banco passa por `run_with_db`,
que executa `asyncio.run` e cria/fecha um cliente **dentro** daquele loop — nenhum cliente assíncrono
é compartilhado entre processos do prefork ou entre loops. A parte de rede (requests, Playwright
síncrono, Instaloader) roda fora de qualquer loop.

## Início rápido

Pré-requisitos: Docker e Docker Compose v2.

```bash
cp .env.example .env
```

Preencha os segredos do `.env` (ver próxima seção) e suba tudo:

```bash
docker compose up --build -d
```

Crie o administrador (pede a senha no terminal):

```bash
docker compose run --rm api python -m app.cli.create_admin --email voce@agencia.com.br --name "Seu Nome"
```

Acesse **http://localhost:8080**. Documentação da API: http://localhost:8080/api/docs.

A ordem de inicialização é garantida por healthchecks: `mongo`/`redis` saudáveis → `init` aplica
migrações e termina → `api`, `worker`, `scheduler` → `frontend`. Os serviços tentam reconectar
ao MongoDB/Redis na inicialização.

## Configuração do ambiente

Todas as variáveis estão documentadas em [.env.example](.env.example). Obrigatórias (o Compose
recusa subir sem elas — não existem senhas padrão):

| Variável | Uso |
|---|---|
| `SECRET_KEY` | Assinatura dos tokens de login (mín. 32 caracteres) |
| `MONGO_ROOT_USER` / `MONGO_ROOT_PASSWORD` | Usuário administrativo do MongoDB (só para manutenção/backup) |
| `MONGO_APP_USER` / `MONGO_APP_PASSWORD` | Usuário da aplicação, com `readWrite` apenas no banco da aplicação |
| `REDIS_PASSWORD` | Senha do Redis |

Gere valores com `openssl rand -hex 32`. Use apenas letras e números nas senhas do MongoDB/Redis
(elas entram em URIs de conexão).

> O usuário da aplicação no MongoDB é criado por `infra/mongo-init/01-create-app-user.js` **somente
> na primeira inicialização** do volume. Para trocar a senha depois, altere-a no MongoDB
> (`db.changeUserPassword`) e no `.env`.

Outras opções úteis: `FRONTEND_BIND`/`FRONTEND_PORT` (por padrão só esta máquina acessa;
use `0.0.0.0` atrás de um proxy HTTPS para acesso na rede), `CORS_ORIGINS` (apenas se outro
endereço precisar chamar a API diretamente, por exemplo o Vite em desenvolvimento),
`SCRAPER_*`, `INSTAGRAM_*`, `TASK_*`.

## Primeiro administrador

```bash
docker compose run --rm api python -m app.cli.create_admin --email admin@agencia.com.br --name "Admin"
```

- A senha (mín. 12 caracteres) é pedida duas vezes e armazenada com Argon2id.
- Automação: `--password-stdin` lê a senha da entrada padrão.
- Redefinir senha: acrescente `--reset`.
- O login tem limite de tentativas por IP + e-mail (`LOGIN_MAX_ATTEMPTS` em `LOGIN_WINDOW_SECONDS`).

## Cadastro de empresas

Menu **Empresas → Nova empresa**:

- **Nome, site, URL do estoque, parser, Instagram, segmento, cidade/UF, observações, status.**
- **Instagram**: aceita `perfil`, `@perfil`, `instagram.com/perfil` ou URL completa; é normalizado para o username.
- **URLs** são validadas: só `http/https`, sem credenciais, sem IPs privados/locais, sem nomes internos (`localhost`,
  `*.internal`, nomes dos serviços do Compose), portas 80/443/8080/8443. Na coleta, o domínio é resolvido e **cada
  redirecionamento** é revalidado; o fetcher também confere o IP efetivamente conectado.
- **Parser de estoque**: `auto` escolhe pelo domínio (`azulpremium.com.br` → `azul`, `grupohazul.com.br` → `hazul`,
  `avancepremium.com.br` → `avance`) e usa `generic` nos demais. `playwright` renderiza páginas com JavaScript;
  com "carregar mais" ativo, clica apenas em botões "carregar/mostrar mais".
- **Frequências** (horas; 0 = somente manual). O Instagram tem intervalo mínimo no servidor (`INSTAGRAM_MIN_FREQUENCY_HOURS`).
- **Concorrentes**: até 20 empresas para os comparativos e o briefing.
- Desativar mantém todo o histórico e interrompe as coletas agendadas.

Na lista e no detalhe há ações para coletar estoque, coletar Instagram, ver o histórico de execuções,
abrir o dashboard e gerar briefing.

### Adicionar um novo site
Crie `backend/app/services/inventory/parsers/<site>.py` com uma classe que implemente
`collect(url, fetchers, options) -> ParseResult` (veja `azul.py`), registre-a em `parsers/__init__.py`
e adicione uma fixture HTML reduzida + teste em `backend/tests/test_parsers.py`.

## Coletas e agendamento

- **Manual**: botões "Coletar estoque"/"Coletar Instagram". A API responde `202` com `run_id`/`task_id`
  imediatamente; o worker executa. Se já houver coleta ativa para a mesma empresa e fonte, a existente é devolvida.
- **Agendada**: o `scheduler` dispara `scheduler_tick` a cada `SCHEDULER_TICK_SECONDS`; o tick cria execuções
  para empresas ativas cuja última execução passou da frequência configurada. Cada agendamento tem
  `idempotency_key` única (`sched:<fonte>:<empresa>:<frequência>:<janela>`), então ticks repetidos não duplicam.
- **Concorrência**: índice único parcial em `collection_runs.active_key` impede duas execuções ativas por
  empresa/fonte; o worker ainda usa um lock no Redis por empresa (estoque) e por perfil (Instagram).
  Entregas duplicadas da mesma tarefa são ignoradas (`start_run` só transiciona `queued → running` uma vez).
- **Falhas transitórias** (timeout, 5xx, 429, conexão) têm novas tentativas limitadas (`TASK_MAX_RETRIES`)
  com espera progressiva (`TASK_RETRY_BACKOFF_SECONDS × 2^n`). Ao detectar limite do Instagram, todas as
  coletas do Instagram pausam por `INSTAGRAM_BLOCK_MINUTES` (dobrando a cada nova ocorrência).
- Execuções sem resposta dentro do lease (`RUN_LEASE_MINUTES`) são marcadas como `abandoned`; execuções que
  ficaram em fila (ex.: broker indisponível) são reenviadas pelo agendador.
- O estado de cada execução fica em `collection_runs` (MongoDB), independente do backend do Celery.
  Tela **Coletas e logs**: empresa, fonte, ID, início/término, status, registros, parcial, mensagem e próxima coleta.

### Regras do estoque
- Só marca um anúncio como **"não encontrado na última coleta"** após coleta **completa e bem-sucedida**.
- A coleta é **parcial** quando: alguma página falhou; o limite de páginas interrompeu a leitura; o site
  anuncia um total maior que o extraído; ou, sem total anunciado, o número caiu abaixo de `INVENTORY_MIN_RATIO`
  dos ativos anteriores. Coleta parcial atualiza o que foi visto, sem remover nada.
- Coleta sem nenhum veículo é **falha**: nada muda no estoque.
- "Não encontrado" **não** é venda: nada é contabilizado como vendido.

**Chave estável do anúncio** (`vehicle_key`): `id:<ID da origem>` → `url:<hash da URL normalizada>` →
`attr:<hash de marca|modelo|versão|ano|km>`. Limitações da última: se a loja editar versão/km, o anúncio
vira "novo" e o antigo "não encontrado"; dois carros idênticos sem link/ID colapsam (contados em
`duplicates_discarded`). O preço nunca entra na chave.

## Sessão de consulta do Instagram (opcional)

Sem sessão, o Instaloader tenta ler dados públicos anonimamente. **Não há garantia**: o Instagram pode exigir
login, limitar consultas, ocultar curtidas ou mudar a estrutura — essas situações aparecem como coleta com
falha ou parcial (com código do motivo), e o último resultado válido é preservado. Nada é contornado.

Se for necessário, use uma **conta de consulta da própria equipe** (nunca a senha da empresa monitorada).
Riscos: a conta pode ser desafiada ou restringida pelo Instagram.

1. Gere o arquivo de sessão (pede a senha só no seu terminal; nada é salvo no projeto além do arquivo de sessão):

   ```bash
   docker compose run --rm --user root -v "$(pwd)/secrets/instagram:/out" worker sh -c 'instaloader --login CONTA_DE_CONSULTA --sessionfile /out/session-CONTA_DE_CONSULTA && chown 10001 /out/session-CONTA_DE_CONSULTA && chmod 600 /out/session-CONTA_DE_CONSULTA'
   ```

2. No `.env`:

   ```
   INSTAGRAM_SESSION_FILE=/run/secrets/instagram/session-CONTA_DE_CONSULTA
   INSTAGRAM_SESSION_USERNAME=CONTA_DE_CONSULTA
   ```

3. `docker compose up -d worker`.

`secrets/` está no `.gitignore` e no `.dockerignore`; o arquivo é montado somente leitura **apenas no worker**.
Cookies, tokens e senhas são removidos dos logs por um filtro de redação.

A integração autorizada com a **API oficial** está preparada como provedor (`OfficialGraphApiProvider`,
`INSTAGRAM_PROVIDER=official_api`) mas não implementada neste MVP.

## Indicadores e regras

**Interação pública estimada** (por publicação):

```
(curtidas + comentários) / seguidores × 100
```

- Seguidores: snapshot válido mais próximo da publicação (±`INSTAGRAM_FOLLOWERS_TOLERANCE_DAYS`); sem
  snapshot próximo, usa os seguidores da coleta em que as métricas foram observadas — a tela informa qual base e data.
- Publicações sem curtidas **ou** comentários visíveis ficam fora do cálculo (não viram zero). O `n` é sempre exibido.
- Não é engajamento por alcance. Alcance, salvamentos, compartilhamentos, visitas e vendas não são públicos e não são exibidos.

**Crescimento de seguidores**: só snapshots reais (sucesso/parcial com seguidores). Base = último snapshot até o
início do período (ou o primeiro dentro dele); fim = último até o fim. Menos de dois snapshots, ou menos de ~1 dia
entre eles, resulta em **"histórico insuficiente"** — nunca em crescimento zero. As datas reais e a cobertura do
período são exibidas; não se promete uma janela exata de 30 dias.

**Frequência de publicação**: o provedor lê as publicações mais recentes (`INSTAGRAM_POSTS_LIMIT`, além das fixadas).
Se a amostra não alcança o início do período, a contagem aparece como mínimo ("≥") com aviso de amostra parcial.
Publicações fixadas (antigas, no topo) são identificadas e não contam para essa verificação.

Zero × indisponível: no banco, `null` = indisponível e `0` = zero observado; na interface, "indisponível"/"sem dado".

## Logs

```bash
docker compose logs -f worker
```

```bash
docker compose logs -f api scheduler
```

A tela **Coletas e logs** mostra o resumo de cada execução (com detalhes técnicos sem segredos ao clicar na linha).
Mensagens de erro são resumidas e passam pelo filtro de redação antes de serem gravadas.

## Exportações e briefings

- **Estoque**: tela Estoque (ou aba Estoque da empresa) → CSV (separador `;`, UTF-8 com BOM, abre no Excel)
  ou Excel (abas Estoque, Ranking Marcas, Ranking Modelos quando filtrado por empresa). Os filtros aplicados valem na exportação.
- **Instagram**: aba Instagram → CSV/Excel com publicações (métricas, interação estimada, base de seguidores) e snapshots.
- **Briefing**: aba Briefing → "Gerar nova versão". Cada versão salva os dados usados (`facts`) e o conteúdo
  (pautas, hipóteses, perguntas, dados necessários, fontes e limitações); consultá-la depois não muda com novas
  coletas. Downloads: **DOCX** e **JSON** (dados usados). As sugestões seguem regras transparentes descritas em
  `backend/app/services/briefing/rules.py`, cada uma com o dado que a motivou; fatos e hipóteses ficam separados.
- **Associação publicação ↔ anúncio**: só manual (aba Instagram → "Associar"), com registro de quem associou.

API equivalente (com `Authorization: Bearer <token>`): `GET /api/exports/vehicles.csv|xlsx`,
`GET /api/exports/companies/{id}/instagram-posts.csv|xlsx`, `GET /api/briefings/{id}/docx|json`.

## Backup e restauração do MongoDB

O diretório `./backups` do host é montado em `/backups` no container do MongoDB.

Backup:

```bash
docker compose exec mongo sh -c 'mongodump -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db "$MONGO_INITDB_DATABASE" --gzip --archive=/backups/monitor-$(date +%Y%m%d-%H%M).gz'
```

Restauração (substitui as coleções existentes; pare `worker`, `scheduler` e `api` antes):

```bash
docker compose stop api worker scheduler
```

```bash
docker compose exec mongo sh -c 'mongorestore -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --gzip --archive=/backups/ARQUIVO.gz --drop'
```

```bash
docker compose up -d
```

Os volumes `mongo_data`, `mongo_config` e `redis_data` persistem entre reinícios. `docker compose down -v` apaga tudo.

## Dados demonstrativos

Opcionais, fictícios e identificados (prefixo `[DEMO]`, `is_demo=true`, origem `demo`). Nunca substituem coletas reais.

```bash
docker compose run --rm api python -m app.cli.seed_demo
```

```bash
docker compose run --rm api python -m app.cli.seed_demo --remove
```

## Testes e validação

```bash
docker compose --profile test run --rm tests
```

Sobe um MongoDB efêmero só para testes (rede isolada, sem internet). Cobrem: normalização e deduplicação, parsers
com fixtures, completude/coleta parcial, preservação do estoque após falhas, reaparecimento e alteração de preço,
crescimento e histórico insuficiente, métricas indisponíveis, amostra parcial e publicações fixadas,
idempotência das execuções (active_key, idempotency_key, lease, entrega duplicada), validação de URLs
(incluindo redirecionamentos para destinos internos) e redação de segredos nos logs.

Desenvolvimento do frontend (com a API acessível em `localhost:8000`): `cd frontend && npm install && npm run dev`.

## Modelo de dados

| Coleção | Conteúdo | Índices principais |
|---|---|---|
| `users` | administradores (hash Argon2id) | `email` único |
| `companies` | cadastro, frequências, concorrentes, resumos (`inventory_summary`, `instagram_summary`) | `slug` único, `active+name_lower` |
| `vehicles` | um documento por anúncio (estado atual, primeira/última observação, status) | `(company_id, vehicle_key)` único |
| `inventory_observations` | uma linha por anúncio por coleta (preço, presença, alteração) | `(vehicle_id, run_id)` único |
| `instagram_profiles` | perfil e último resultado válido (`latest`) | `username` único |
| `instagram_snapshots` | cada coleta/entrada manual: data, origem, status, contagens, responsável | `(profile_id, collected_at)`, `(profile_id, run_id)` único |
| `instagram_posts` | publicação única por `(profile_id, shortcode)`; `latest_metrics` | `(profile_id, shortcode)` único |
| `instagram_post_metrics` | observação de curtidas/comentários por coleta | `(post_id, run_id)` único |
| `collection_runs` | execuções (status, tentativas, parcial, erro resumido, detalhes) | `idempotency_key` e `active_key` únicos parciais |
| `briefings` | versões congeladas (dados + conteúdo) | `(company_id, version)` único |
| `post_vehicle_links` | associações manuais publicação ↔ anúncio | `(post_id, vehicle_id)` único |
| `schema_migrations` | versões aplicadas + trava de migração | — |

Históricos ficam em coleções próprias (sem arrays crescendo dentro de documentos). Datas em UTC; exibição em
America/Sao_Paulo. Não há índices TTL. Migrações em `backend/app/db/migrations.py` são versionadas e idempotentes
e rodam apenas no serviço `init`.

## Limitações conhecidas

- **Sites mudam**: os parsers foram verificados em 30/10/2026 (Azul 102/102, Hazul 6/6, Avance 26/26 anúncios).
  Mudanças de layout ou endpoint podem quebrar um parser; o sistema registra falha/parcial e preserva o estoque.
  O parser Avance depende do endpoint `admin-ajax.php` usado pela página; como alternativa, troque para `playwright`.
- **Parser genérico/Playwright** é heurístico e não conhece o total anunciado; a completude depende da regra de queda brusca.
- **Hazul**: o modelo vem do JSON-LD da página; sem ele, a primeira palavra do título vira o modelo.
- **Instagram**: funcionamento não garantido; coletas anônimas podem ser bloqueadas a qualquer momento. Em 30/10/2026 a
  contagem total de publicações do perfil (`media_count`) não veio na resposta e os formatos Reels aparecem como "vídeo".
  A fixação de posts é inferida pela ordem cronológica quando não informada.
- **Histórico** começa na primeira coleta; nada anterior é estimado.
- **Tempo observado** ≠ tempo real em estoque; **não encontrado** ≠ vendido.
- **DNS rebinding**: mitigado (revalidação por salto e verificação do IP conectado), não eliminado; o navegador
  (Playwright) bloqueia sub-requisições para destinos internos, mas redirecionamentos de navegação são verificados após ocorrerem.
- A tabela da visão geral calcula indicadores dependentes do período no servidor para até 500 empresas filtradas.
- Autenticação é administrativa simples (todos os usuários são administradores); o token fica no `localStorage`.
- Para acesso fora da máquina local, publique o frontend atrás de HTTPS.
