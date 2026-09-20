from uuid import uuid4

from fastapi.testclient import TestClient

from company_service.application import app

client = TestClient(app)


def test_accept_message_response_event() -> None:
    response = client.post(
        "/webhooks/ai-support",
        headers={"Authorization": "Bearer hook-secret"},
        json={
            "event": "message.response",
            "conversation_id": str(uuid4()),
            "in_reply_to_message_id": str(uuid4()),
            "message": {
                "id": str(uuid4()),
                "author": "assistant",
                "content": "Your order is on its way.",
            },
            "confidence": 95,
            "intent": "order_status",
            "sources": [],
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_accept_handoff_event() -> None:
    response = client.post(
        "/webhooks/ai-support",
        headers={"Authorization": "Bearer hook-secret"},
        json={
            "event": "conversation.handoff_required",
            "conversation_id": str(uuid4()),
            "message_id": str(uuid4()),
            "handoff_id": str(uuid4()),
            "reason": "payment_issue",
            "intent": "payment_issue",
            "confidence": 42,
            "rewritten_query": "The customer has a payment issue.",
            "tools": [],
            "sources": [],
        },
    )

    assert response.status_code == 202


def test_webhook_rejects_unknown_event() -> None:
    response = client.post(
        "/webhooks/ai-support",
        headers={"Authorization": "Bearer hook-secret"},
        json={"event": "unknown"},
    )

    assert response.status_code == 422

