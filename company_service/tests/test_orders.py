from fastapi.testclient import TestClient

from company_service.application import app

client = TestClient(app)


def test_get_known_order() -> None:
    response = client.get(
        "/orders/ORD-1001",
        headers={"Authorization": "Bearer orders-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_number"] == "ORD-1001"
    assert len(payload["items"]) == 2
    assert payload["tracking_number"] == "DHL-PL-84001001"


def test_get_unknown_order_returns_404() -> None:
    response = client.get(
        "/orders/ORD-9999",
        headers={"Authorization": "Bearer orders-secret"},
    )

    assert response.status_code == 404


def test_orders_require_their_own_token() -> None:
    response = client.get("/orders/ORD-1001")

    assert response.status_code == 401
