from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.assets import UPLOAD_DIR
from app.api.assets import router as assets_router
from app.api.health import router as health_router
from app.config import settings
from app.game.server import server
from app.ws.game import router as game_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await server.load()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(assets_router)
app.include_router(game_router)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
