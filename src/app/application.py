"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.knowledge import router as knowledge_router
from app.core.config import get_settings
from app.messaging.knowledge import RabbitMQKnowledgeJobs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    jobs = RabbitMQKnowledgeJobs(
        url=settings.rabbitmq_url,
        queue_name=settings.knowledge_queue_name,
    )
    app.state.knowledge_jobs = jobs
    yield
    await jobs.close()


def create_app() -> FastAPI:
    application = FastAPI(title="AI Support Platform", lifespan=lifespan)
    application.include_router(knowledge_router)
    return application


app = create_app()
