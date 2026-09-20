"""Single background process for knowledge indexing and conversation work."""

import asyncio

from app.core.config import get_settings
from app.providers.embeddings import create_embedding_provider
from app.workers.conversations import run as run_conversations
from app.workers.knowledge import run as run_knowledge


async def run() -> None:
    embedding_provider = create_embedding_provider(get_settings())
    await asyncio.gather(
        run_knowledge(embedding_provider),
        run_conversations(embedding_provider),
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
