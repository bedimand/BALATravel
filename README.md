# BALATravel

Planejador de viagens autônomo com IA que cria itinerários completos, dia a dia, usando um agente LLM com capacidade de chamada de ferramentas. O agente busca lugares, raciocina sobre geografia, horários de funcionamento, clima e preferências do viajante, e então constrói um cronograma que uma pessoa real pode seguir.

## Como Funciona

O núcleo do BALATravel é o **CentralMind** — um loop de agente autônomo que:

1. **Busca** lugares via Google Maps (SerpApi) e OpenTripMap, encontrando restaurantes, museus, pontos turísticos, mercados, igrejas, parques e vida noturna
2. **Raciocina** sobre o perfil do viajante (interesses, ritmo, restrições alimentares, mobilidade) e contexto da viagem (datas, orçamento, localização da hospedagem, previsão do tempo)
3. **Constrói o itinerário** atividade por atividade usando chamadas `place_item` — decidindo o que vai onde, por quanto tempo e por quê
4. **Auto-verifica** o cronograma antes de finalizar: confirmando que almoço/jantar existem, sem lacunas, sem lugares duplicados, e que o fluxo geográfico faz sentido
5. **Auto-corrige** quando encontra problemas — removendo posicionamentos ruins e substituindo-os

O LLM é responsável por todas as decisões de agendamento. Não existe algoritmo determinístico — o agente decide durações, ordem das atividades, agrupamento geográfico e diversidade de categorias com base no seu entendimento sobre viagens.

## Arquitetura

```
backend/
  app/
    api/routes/       # Endpoints REST (trips, auth, agent, share)
    core/             # Config, banco de dados, segurança
    models/           # Entidades SQLAlchemy (Trip, Place, ItineraryVersion, etc.)
    schemas/          # Modelos Pydantic de request/response
    services/
      central_mind.py   # Loop do agente autônomo (CentralMind)
      tool_registry.py  # 20 ferramentas que o agente pode chamar
      agent.py          # AgentCoordinator (tratamento reativo de mensagens)
      agent_tools.py    # Implementações das ferramentas (busca, posicionar, editar)
      workflow.py       # Orquestração de workflows multi-etapa
      providers.py      # Adaptadores Google Maps, SerpApi, OpenTripMap
      routing.py        # Integração com Google Routes API
      weather.py        # Previsão do tempo OpenWeather
      llm.py            # Abstração de chat LLM (compatível com OpenAI)
      planner.py        # Construtor de payload do mapa
      exports.py        # Exportação PDF/JSON
      shares.py         # Links compartilháveis de viagem

frontend/
  app/
    page.tsx            # Página inicial
    login/              # Autenticação
    signup/
    profile/            # Preferências do usuário
    trips/new/          # Wizard de criação de viagem
    trips/[id]/         # Workspace do planejador (mapa + itinerário)
    history/            # Viagens anteriores
```

## Ferramentas do Agente

O agente LLM tem acesso a 20 ferramentas:

| Ferramenta | Finalidade |
|------------|-----------|
| `search_places_by_interest` | Buscar no Google Maps com consultas descritivas |
| `search_places_general` | Descoberta ampla via OSM + OpenTripMap |
| `get_weather_forecast` | Condições climáticas para as datas da viagem |
| `estimate_route` | Tempo de deslocamento entre duas coordenadas |
| `list_saved_places` | Revisar todos os lugares salvos com horários, localização, avaliações |
| `get_day_context` | Clima + itens posicionados + lugares restantes ordenados por distância |
| `start_itinerary` | Criar cronograma vazio |
| `place_item` | Posicionar uma atividade em data/hora específica (calcula deslocamento automaticamente) |
| `get_day_schedule` | Visualizar itens posicionados em um dia específico |
| `finalize_itinerary` | Validar e finalizar o cronograma |
| `update_item` / `remove_item` / `insert_item` | Editar itens existentes |
| `reorder_day` | Otimizar a sequência de um dia por proximidade |
| `check_route` | Verificar tempo de deslocamento antes de confirmar |
| `finish` | Sinalizar conclusão |

## Executando o Projeto

### Pré-requisitos

- Python 3.11+
- Node.js 18+ e npm
- Chaves de API (veja a seção de Ambiente abaixo)

### 1. Instalar Node.js e npm no Windows

O npm já vem incluído com o Node.js. A forma mais fácil de instalar é pelo **winget**, que já vem embutido no Windows 10/11:

```bash
winget install OpenJS.NodeJS.LTS
```

Feche e reabra o terminal depois de instalar. Verifique:

```bash
node --version    # deve mostrar v18.x ou superior
npm --version     # deve mostrar 9.x ou superior
```

> **Alternativa — instalador gráfico:**
> Acesse [https://nodejs.org](https://nodejs.org), baixe o instalador LTS (.msi) e siga o wizard mantendo as opções padrão.

### 2. Instalar Python no Windows

```bash
winget install Python.Python.3.11
```

Feche e reabra o terminal depois de instalar. Verifique:

```bash
python --version   # deve mostrar 3.11 ou superior
pip --version
```

> **Alternativa — instalador gráfico:**
> Acesse [https://www.python.org/downloads/](https://www.python.org/downloads/), baixe o instalador e **marque "Add Python to PATH"** antes de clicar em Install.

### 3. Clonar o repositório e configurar o backend

```bash
cd backend

# Criar ambiente virtual
python -m venv .venv

# Ativar o ambiente virtual (Windows)
.venv\Scripts\activate

# Instalar dependências
pip install -e .[dev]
```

### 4. Configurar variáveis de ambiente

Crie o arquivo `backend/.env`:

```env
# LLM (obrigatório — qualquer endpoint compatível com OpenAI)
OPENAI_BASE_URL=https://seu-endpoint-llm/openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0

# Busca de lugares (obrigatório para planejamento de viagens)
SERPAPI_API_KEY=...          # Busca de lugares no Google Maps via SerpApi

# Rotas (obrigatório para cálculo de tempo de deslocamento)
GOOGLE_ROUTES_API_KEY=...

# Opcional — enriquece resultados mas não é estritamente necessário
OPENTRIPMAP_API_KEY=...     # Enriquecimento de lugares (avaliações, resumos)
OPENWEATHER_API_KEY=...     # Previsão do tempo para agendamento

# Opcional: OpenRouter como LLM alternativo/fallback
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Crie o arquivo `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api
```

### 5. Iniciar o backend

```bash
cd backend
uvicorn app.main:app --reload
```

A API estará disponível em `http://127.0.0.1:8000`. Documentação em `http://127.0.0.1:8000/docs`.

O banco de dados (SQLite) é criado automaticamente na primeira execução.

### 6. Iniciar o frontend

```bash
cd frontend
npm install
npm run dev
```

A aplicação estará disponível em `http://localhost:3000`.

### 7. Usar a aplicação

1. Crie uma conta em `http://localhost:3000/signup`
2. Crie uma nova viagem em `http://localhost:3000/trips/new`
3. O agente vai buscar lugares autonomamente e construir seu itinerário
4. Use o chat para fazer edições ("mover o jantar para mais cedo", "adicionar um dia de praia", etc.)

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/auth/register` | Criar conta |
| POST | `/api/auth/login` | Obter tokens JWT |
| POST | `/api/trips` | Criar uma viagem |
| POST | `/api/trips/{id}/search` | Buscar voos, hotéis, lugares |
| POST | `/api/trips/{id}/itinerary/generate` | Disparar planejamento autônomo |
| POST | `/api/trips/{id}/itinerary/replan` | Reconstruir itinerário |
| POST | `/api/trips/{id}/agent/message` | Conversar com o agente (edições reativas) |
| GET | `/api/trips/{id}/workspace` | Estado completo do workspace |
| GET | `/api/trips/{id}/map` | Marcadores + rotas do mapa |
| POST | `/api/trips/{id}/export/{format}` | Exportar PDF/JSON |
| POST | `/api/trips/{id}/share` | Criar link compartilhável |

## Como o Agente Planeja

Quando acionado, o agente CentralMind segue esta estrutura:

```
Buscar (4-6 consultas diversas)
  → Listar lugares salvos (revisar o pool)
    → Obter previsão do tempo
      → Iniciar itinerário
        → Para cada dia:
            Obter contexto do dia (clima, proximidade, lugares restantes)
            Posicionar o dia inteiro em um lote:
              Manhã: locais culturais, museus (09:00-12:00)
              Almoço: restaurante (12:30-14:00)
              Tarde: mercados, igrejas, parques (14:30-18:00)
              Entardecer: caminhada, mirante, bar (18:00-19:30)
              Jantar: restaurante (19:30-21:00)
        → Auto-verificar todos os dias
        → Corrigir problemas
        → Finalizar
```

O agente garante:
- Almoço E jantar todos os dias
- Sem lacunas >1h entre atividades
- Sem mesma categoria em sequência
- Sem lugares repetidos entre dias
- Agrupamento geográfico (minimizar deslocamentos)
- Todos os dias da viagem cobertos (intervalo de datas inclusivo)

## Testes

```bash
cd backend
pytest tests/ -v
```

## Stack Tecnológica

- **Backend:** Python 3.11, FastAPI, SQLAlchemy, SQLite
- **Frontend:** Next.js 15, React 19, MapLibre GL, TypeScript
- **LLM:** Qualquer endpoint compatível com OpenAI (testado com Claude Sonnet 4.5 no Bedrock)
- **Busca:** SerpApi (Google Maps), OpenTripMap, Nominatim
- **Rotas:** Google Routes API
- **Clima:** OpenWeather API
