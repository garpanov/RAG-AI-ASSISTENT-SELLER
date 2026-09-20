"""In-memory order repository used instead of a database."""

from datetime import UTC, datetime

from company_service.schemas import Order, OrderItem


class OrderRepository:
    def __init__(self) -> None:
        self._orders = {order.order_number: order for order in _orders()}

    async def get(self, order_number: str) -> Order | None:
        return self._orders.get(order_number)


def _orders() -> tuple[Order, ...]:
    return (
        Order(
            order_number="ORD-1001",
            name="Home office starter kit",
            items=[
                OrderItem(sku="KB-101", name="Mechanical keyboard", quantity=1, unit_price=89.90),
                OrderItem(sku="MS-205", name="Wireless mouse", quantity=1, unit_price=39.50),
            ],
            total_price=129.40,
            currency="EUR",
            created_at=datetime(2026, 9, 10, 9, 15, tzinfo=UTC),
            status="delivered",
            shipped_at=datetime(2026, 9, 11, 12, 30, tzinfo=UTC),
            tracking_number="DHL-PL-84001001",
        ),
        Order(
            order_number="ORD-1002",
            name="Developer monitor order",
            items=[OrderItem(sku="MN-427", name="27-inch 4K monitor", quantity=1, unit_price=449.00)],
            total_price=449.00,
            currency="EUR",
            created_at=datetime(2026, 9, 12, 14, 5, tzinfo=UTC),
            status="shipped",
            shipped_at=datetime(2026, 9, 14, 8, 20, tzinfo=UTC),
            tracking_number="UPS-1Z9991002",
        ),
        Order(
            order_number="ORD-1003",
            name="Video call accessories",
            items=[
                OrderItem(sku="CM-033", name="Full HD webcam", quantity=1, unit_price=74.00),
                OrderItem(sku="LT-018", name="LED desk light", quantity=2, unit_price=24.50),
            ],
            total_price=123.00,
            currency="EUR",
            created_at=datetime(2026, 9, 15, 16, 45, tzinfo=UTC),
            status="processing",
            shipped_at=None,
            tracking_number=None,
        ),
        Order(
            order_number="ORD-1004",
            name="Ergonomic workspace",
            items=[OrderItem(sku="CH-700", name="Ergonomic chair", quantity=1, unit_price=329.99)],
            total_price=329.99,
            currency="EUR",
            created_at=datetime(2026, 9, 5, 11, 0, tzinfo=UTC),
            status="cancelled",
            shipped_at=None,
            tracking_number=None,
        ),
        Order(
            order_number="ORD-1005",
            name="USB-C travel set",
            items=[
                OrderItem(sku="HB-440", name="USB-C hub", quantity=1, unit_price=55.00),
                OrderItem(sku="CB-120", name="USB-C cable", quantity=2, unit_price=12.00),
            ],
            total_price=79.00,
            currency="EUR",
            created_at=datetime(2026, 9, 16, 7, 30, tzinfo=UTC),
            status="shipped",
            shipped_at=datetime(2026, 9, 17, 10, 10, tzinfo=UTC),
            tracking_number="DPD-PL-55001005",
        ),
        Order(
            order_number="ORD-1006",
            name="Audio equipment",
            items=[OrderItem(sku="HP-808", name="Noise-cancelling headphones", quantity=1, unit_price=219.00)],
            total_price=219.00,
            currency="EUR",
            created_at=datetime(2026, 9, 18, 13, 25, tzinfo=UTC),
            status="processing",
            shipped_at=None,
            tracking_number=None,
        ),
        Order(
            order_number="ORD-1007",
            name="Team onboarding bundle",
            items=[
                OrderItem(sku="KB-101", name="Mechanical keyboard", quantity=3, unit_price=89.90),
                OrderItem(sku="MS-205", name="Wireless mouse", quantity=3, unit_price=39.50),
                OrderItem(sku="HS-310", name="USB headset", quantity=3, unit_price=48.00),
            ],
            total_price=532.20,
            currency="EUR",
            created_at=datetime(2026, 9, 8, 8, 0, tzinfo=UTC),
            status="delivered",
            shipped_at=datetime(2026, 9, 9, 15, 40, tzinfo=UTC),
            tracking_number="GLS-PL-72001007",
        ),
    )

