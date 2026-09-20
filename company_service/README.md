# Example Company Service

An entirely standalone example of a company's integration API. It does not
import code from the parent AI support project, use its database, or share its
Python environment. The root `compose.yaml` is only a convenient way to run the
two independently built applications on the same Docker network.

The service exposes exactly two integration endpoints:

- `GET /orders/{order_number}` returns one of seven hard-coded orders.
- `POST /webhooks/ai-support` receives `message.response` and
  `conversation.handoff_required` events and writes the accepted event to the
  container log.

Both endpoints expect `Authorization: Bearer <secret>`. Configure the secrets
with `ORDERS_API_KEY` and `WEBHOOK_SECRET`.

## Run independently

```bash
cp .env.example .env
docker build -t example-company-service .
docker run --rm --env-file .env -p 8080:8080 example-company-service
```

Example request:

```bash
curl -H 'Authorization: Bearer local-company-key' \
  http://localhost:8080/orders/ORD-1001
```

## Run with the AI support platform

From the parent repository:

```bash
docker compose up --build
```

The Compose network configures the support worker to call this service by its
container hostname. The company service remains independently buildable and
deployable.

## Check the project

```bash
uv sync
uv run ruff check .
uv run mypy .
uv run pytest
```

