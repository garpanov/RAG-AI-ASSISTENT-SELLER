<div align="center">

# AI Support Platform

### A company-owned RAG and order-support layer that answers routine questions and hands complex cases to people.

The platform accepts customer messages, searches an internal knowledge base, retrieves
order data when necessary, generates an answer with an LLM, and delivers the result to
the company's system through a webhook.

[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/vector_search-pgvector-4169E1)](https://github.com/pgvector/pgvector)
[![RabbitMQ](https://img.shields.io/badge/queue-RabbitMQ-FF6600?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![mypy](https://img.shields.io/badge/types-mypy-2A6DB2)](https://mypy-lang.org/)

</div>

---

> [!CAUTION]
> **This project is middleware, not an authorization boundary.** The current
> implementation performs almost no end-user access checks for order information.
> The worker calls the configured Orders API with one service credential and does not
> prove that the customer who supplied an order number owns or may view that order.
> The public conversation and admin knowledge endpoints also have no built-in
> authentication middleware.
>
> A company integrating this platform must design and enforce its own authentication,
> tenant isolation, conversation ownership, order-level authorization, network access,
> secret management, rate limiting, audit logging, and data-retention rules. Do not
> expose the service directly to untrusted clients or use the example company service
> as a production security model.

## What it does

| Capability | Description |
|---|---|
| Asynchronous message processing | Accepts a message with HTTP `202`, then processes it through RabbitMQ. |
| RAG knowledge search | Splits company documents, generates embeddings, searches with pgvector, and reranks the best chunks. |
| Order lookup | Lets the planner request `GET /orders/{order_number}` from a company-owned API. |
| Human handoff | Routes low-confidence, dependency-failed, or judgment-heavy cases to a manager workflow. |
| Conversation memory | Keeps the latest 10 messages verbatim and maintains an LLM-generated summary of older messages. |
| Replaceable LLM providers | Supports Gemini and OpenAI-compatible endpoints for planning and final answers. |
| Company webhooks | Sends either a generated response or a handoff event back to the integrating system. |

The current prompts and generated customer answers are English-language.

## How it works

```mermaid
flowchart LR
    A["Company channel or backend"] -->|"POST customer message"| B["FastAPI"]
    B --> C["PostgreSQL"]
    B --> D["RabbitMQ"]
    D --> E["Support worker"]
    E --> F["Planner LLM"]
    F -->|"FAQ needed"| G["pgvector search + reranker"]
    F -->|"Order needed"| H["Company Orders API"]
    G --> I["Answer LLM"]
    H --> I
    I --> J["Company webhook"]
    E -->|"Low confidence or failure"| K["Manager handoff webhook"]
```

Message processing follows these rules:

1. The API stores the customer message and publishes a RabbitMQ job.
2. The planner classifies the request, decides whether RAG or order lookup is needed,
   and reports confidence.
3. RAG retrieves up to `RAG_CANDIDATE_K` chunks and keeps `RAG_TOP_K` after reranking.
4. The answer model receives the question, conversation context, selected chunks, and
   tool results.
5. The platform posts `message.response` to the company webhook. If confidence is below
   the configured threshold, required context is missing, an integration fails, or the
   planner requests human judgment, it posts `conversation.handoff_required` instead.

Gemini planning output is schema-validated with Pydantic. The default `vector` reranker
preserves cosine-distance order and does not load a second model. Set
`RERANKER_PROVIDER=qwen3` to use `Qwen/Qwen3-Reranker-0.6B` locally.

## Architecture

The application uses a deliberately small layered architecture:

```text
Router -> Service -> Repository -> PostgreSQL
              |
              +-> RabbitMQ / LLM / company integrations
```

- **Routers** validate HTTP input and translate domain errors into status codes.
- **Services** own message, RAG, indexing, and handoff business logic.
- **Repositories** contain SQLAlchemy 2 async database access.
- **Providers** isolate embedding, reranking, LLM, Orders API, and webhook adapters.
- **Workers** consume durable RabbitMQ queues for document indexing and conversations.

Schema changes are managed exclusively with Alembic; production startup must run
`alembic upgrade head` rather than `create_all`.

## Quick start with Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose;
- a Gemini API key, or compatible planner and answer endpoints;
- enough memory for the local Qwen embedding model.

### 1. Configure the environment

```bash
cp .env.example .env
```

For the default Gemini configuration, set at least:

```dotenv
ANSWER_API_KEY=your-gemini-api-key
```

`PLANNER_API_KEY` may be left empty; the planner then uses `ANSWER_API_KEY`.
The Compose file supplies local PostgreSQL, RabbitMQ, Orders API, and webhook URLs.

> [!WARNING]
> The values in `compose.yaml` are development defaults. Replace every API key and
> webhook secret before deploying, keep `.env` out of version control, and put the API
> behind the company's authenticated gateway.

### 2. Build infrastructure and apply migrations

```bash
docker compose up --build -d db rabbitmq company-service
docker compose run --rm api alembic upgrade head
```

### 3. Start the API and conversation worker

```bash
docker compose up --build -d api support-worker
```

Open the interactive API documentation at <http://localhost:8000/docs>.

Document indexing requires the separate knowledge worker. The current Compose file
does not define it as a long-lived service, so run it in another terminal:

```bash
docker compose run --rm api python -m app.workers.knowledge
```

Inspect or stop the stack:

```bash
docker compose logs -f api support-worker company-service
docker compose down
```

`docker compose down` preserves named volumes. Add `--volumes` only when you
intentionally want to delete local PostgreSQL, RabbitMQ, and Redis data.

## API

### Customer messages

`POST /v1/conversations/{conversation_id}/messages` creates the conversation on its
first message, stores the message, and returns immediately:

```bash
curl -X POST http://localhost:8000/v1/conversations/01958bea-5c67-7c51-9da9-cf5bdca76e70/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"Where is order ORD-1001?"}'
```

```json
{
  "message_id": "e6c4afc4-d112-4de6-9c3d-56706395d4db",
  "status": "processing"
}
```

The final result is asynchronous and is sent to `COMPANY_WEBHOOK_URL` as one of:

- `message.response` — the assistant produced an answer;
- `conversation.handoff_required` — a manager must continue the conversation.

### Knowledge documents

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/admin/knowledge/documents` | Add a text document and queue indexing |
| `POST` | `/v1/admin/knowledge/documents/upload` | Upload a PDF, DOCX, or TXT document |
| `GET` | `/v1/admin/knowledge/documents` | List documents and indexing status |
| `PATCH` | `/v1/admin/knowledge/documents` | Replace a document and reindex it |
| `DELETE` | `/v1/admin/knowledge/documents/{number_document}` | Delete a document and its chunks |

Example:

```bash
curl -X POST http://localhost:8000/v1/admin/knowledge/documents \
  -H 'Content-Type: application/json' \
  -d '{"number_document":"FAQ-001","content":"Standard delivery takes 3–5 business days."}'
```

Document create and update calls return `202 Accepted`. Their `status` moves through
`pending`, `processing`, `ready`, or `failed` as the knowledge worker runs.

> [!IMPORTANT]
> `/v1/admin/knowledge/*` is named as an admin API but is not currently protected by
> authentication or role checks. Restrict it at the gateway or private network layer.

## Company integration contract

The platform expects two company-owned endpoints:

| Direction | Contract | Authentication |
|---|---|---|
| Platform -> company | `GET {ORDERS_BASE_URL}/orders/{order_number}` | Optional bearer token from `ORDERS_API_KEY` |
| Platform -> company | `POST {COMPANY_WEBHOOK_URL}` | Optional bearer token from `COMPANY_WEBHOOK_SECRET` |

`company_service/` is a standalone demonstration with seven hard-coded orders and
webhook logging. It has its own package, tests, and container image and shares no
application code or database with the main service.

In production, the company-owned Orders API must validate that the calling service and
the end user represented by the conversation may access the requested order. The
current tool contract sends only an order number and a shared service credential, so a
production integration will need to add trustworthy user/tenant context or perform the
authorization before a request ever reaches this platform.

## Configuration

| Variable | Example/default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg_async://...` | Async PostgreSQL connection |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost/` | RabbitMQ connection |
| `KNOWLEDGE_QUEUE_NAME` | `knowledge.documents.index` | Document indexing queue |
| `MESSAGE_QUEUE_NAME` | `conversations.messages.process` | Customer message queue |
| `EMBEDDING_PROVIDER` | `qwen3` | Embedding adapter |
| `EMBEDDING_MODEL_NAME` | `Qwen/Qwen3-Embedding-0.6B` | Local embedding model |
| `EMBEDDING_DIMENSIONS` | `384` | Vector size; the schema currently requires 384 |
| `EMBEDDING_BATCH_SIZE` | `16` | Embedding batch size |
| `KNOWLEDGE_CHUNK_SIZE` | `1200` | Chunk size in normalized characters |
| `KNOWLEDGE_CHUNK_OVERLAP` | `200` | Character overlap between chunks |
| `PLANNER_PROVIDER` | `gemini` | `gemini` or `openai_compatible` |
| `PLANNER_BASE_URL` | Gemini API URL | Planner endpoint base URL |
| `PLANNER_API_KEY` | empty | Planner key; Gemini falls back to `ANSWER_API_KEY` |
| `PLANNER_MODEL_NAME` | `gemini-3.5-flash-lite` | Planner model |
| `PLANNER_TIMEOUT_SECONDS` | `60.0` | Planner request timeout |
| `PLANNER_HANDOFF_CONFIDENCE_THRESHOLD` | `70` | Lower confidence forces handoff |
| `RAG_CANDIDATE_K` | `30` | Vector-search candidate count |
| `RAG_TOP_K` | `5` | Chunks retained after reranking |
| `RERANKER_PROVIDER` | `vector` | `vector` or `qwen3` |
| `RERANKER_MODEL_NAME` | `Qwen/Qwen3-Reranker-0.6B` | Optional local cross-encoder |
| `ANSWER_PROVIDER` | `gemini` | `gemini` or `openai_compatible` |
| `ANSWER_BASE_URL` | Gemini API URL | Final-answer endpoint base URL |
| `ANSWER_API_KEY` | empty | Final-answer provider key |
| `ANSWER_MODEL_NAME` | `gemini-3.6-flash` | Final-answer model |
| `ANSWER_TIMEOUT_SECONDS` | `60.0` | Final-answer request timeout |
| `ORDERS_BASE_URL` | empty | Company Orders API base URL |
| `ORDERS_API_KEY` | empty | Optional Orders API bearer token |
| `COMPANY_WEBHOOK_URL` | empty | Destination for answers and handoffs |
| `COMPANY_WEBHOOK_SECRET` | empty | Optional webhook bearer token |
| `INTEGRATION_TIMEOUT_SECONDS` | `15.0` | Orders API and webhook timeout |

All settings are required to exist in the environment; `.env.example` provides a
complete local template.

## Running without Docker

Install [uv](https://docs.astral.sh/uv/), start reachable PostgreSQL and RabbitMQ
instances, then configure `.env`:

```bash
uv sync --all-groups
uv run alembic upgrade head
```

Run each long-lived process in its own terminal:

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
uv run python -m app.workers.knowledge
```

```bash
uv run python -m app.workers.support
```

## Project structure

```text
.
├── alembic/                   Database migrations
├── company_service/           Standalone example company integration
├── docs/                      Design and MVP notes
├── src/app/
│   ├── api/                   FastAPI routers, schemas, dependencies
│   ├── core/                  Environment configuration
│   ├── database/              Async SQLAlchemy session setup
│   ├── messaging/             RabbitMQ publishers
│   ├── models/                Database entities and enums
│   ├── providers/             LLM, embedding, reranking, HTTP adapters
│   ├── repositories/          Database access
│   ├── services/              Business logic
│   └── workers/               RabbitMQ consumers
├── tests/                     Unit and API tests
├── compose.yaml
├── Dockerfile
└── pyproject.toml
```

## Development

Install development dependencies and run the full quality gate:

```bash
uv sync --all-groups
uv run ruff check .
uv run mypy .
uv run pytest
```

The test suite covers conversation processing and handoff decisions, planner and
answer providers, vector and Qwen reranking, knowledge indexing, document extraction,
and API behavior.

## Current limitations

- End-user authentication and order ownership checks are not implemented.
- Admin knowledge routes are not authenticated.
- The Orders API tool receives an order number but no verified user or tenant identity.
- The Docker Compose stack does not yet declare the knowledge worker as a service.
- Redis is included in Compose but is not used by the current application code.
- Webhook delivery has no persistent retry or dead-letter workflow after processing.
- The platform currently assumes English customer conversations.

Treat these as integration requirements before production deployment, especially the
authorization gaps around order data.
