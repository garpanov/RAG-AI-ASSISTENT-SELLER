# Context
An AI system support platform that can be deployed independently for each company. 
The system handles customer communications regarding the simplest topics and questions, or inquiries about orders or products. 
If a question is specific or involves an order with an issue that requires human judgment, it connects the customer to a manager via chat.  
The main feature is that the system can be implemented individually and independently within each system.

# Architecture

Use:

Router -> Service -> Repository -> Database

Routers contain no business logic.

Services contain business logic.

Repositories contain database access.

# Database

- PostgreSQL + pgvector
- SQLAlchemy 2 async or psycopg
- Alembic migrations
- never use create_all in production

# Code

- Python 3.14
- type hints required
- async where appropriate
- no unnecessary abstractions

# Changes

Before implementing:
1. inspect existing code
2. propose a plan
3. modify the minimum number of files

Never refactor unrelated code.

# Verification

After changes run:

ruff check .
mypy .
pytest

Explain:
- what changed
- why
- possible risks