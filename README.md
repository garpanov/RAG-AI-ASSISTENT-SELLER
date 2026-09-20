# AI Support Platform

## Conversation message processing

`POST /v1/conversations/{conversation_id}/messages` accepts an English customer
message and returns HTTP 202:

```json
{
  "message_id": "e6c4afc4-d112-4de6-9c3d-56706395d4db",
  "status": "processing"
}
```

The `support-worker` process consumes the job, gives the latest 10 database
messages to the Planner LLM, optionally searches FAQ knowledge and calls
`GET /orders/{id}`, then sends either `message.response` or
`conversation.handoff_required` to the company webhook. RAG first retrieves up
to 30 chunks by vector similarity. The default `vector` reranker keeps that
cosine-distance order and selects the best 5 without loading a second local
model. Set `RERANKER_PROVIDER=qwen3` to opt into the
`Qwen/Qwen3-Reranker-0.6B` cross-encoder.

Messages older than the latest 10 are kept in a rolling conversation summary.
The Planner merges only newly expired messages into that stored summary during
its normal request, so summarization does not add another LLM request. The final
answer provider receives the current question, stored summary, latest 10
messages verbatim, five reranked chunks, and tool results.

Required deployment configuration:

- `PLANNER_PROVIDER=gemini`, `PLANNER_MODEL_NAME`, and optional
  `PLANNER_API_KEY` (falls back to `ANSWER_API_KEY` when empty)
- use `PLANNER_PROVIDER=openai_compatible` with an OpenAI-compatible
  `PLANNER_BASE_URL` to run the Planner on another hosted or local model
- `RERANKER_PROVIDER=vector` (default, no second model) or `qwen3`; the latter
  also uses `RERANKER_MODEL_NAME`
- `ANSWER_PROVIDER=gemini`, `ANSWER_API_KEY`, and `ANSWER_MODEL_NAME`
- use `ANSWER_PROVIDER=openai_compatible` with `ANSWER_BASE_URL` to switch to
  another hosted or local OpenAI-compatible model
- `ORDERS_BASE_URL` and optional `ORDERS_API_KEY`
- `COMPANY_WEBHOOK_URL` and optional `COMPANY_WEBHOOK_SECRET`

The worker treats Planner confidence below
`PLANNER_HANDOFF_CONFIDENCE_THRESHOLD` (default 70), missing required RAG data,
or a failed required tool as a manager handoff. Apply database migrations with
`alembic upgrade head` before starting the API and worker.
