"""FastAPI entrypoint for the standalone example company service."""

from fastapi import FastAPI

from company_service.routers import router


def create_app() -> FastAPI:
    application = FastAPI(title="Example Company Integration")
    application.include_router(router)
    return application


app = create_app()

