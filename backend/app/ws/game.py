from fastapi import APIRouter, WebSocket

from app.game.server import server

router = APIRouter()


@router.websocket("/ws/game")
async def game_socket(ws: WebSocket) -> None:
    await ws.accept()
    await server.serve(ws)
