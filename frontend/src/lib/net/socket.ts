import type { ClientMessage, ServerMessage } from './protocol'

export type ConnectionStatus = 'connecting' | 'online' | 'offline'

interface Handlers {
  onOpen: () => void
  onMessage: (msg: ServerMessage) => void
  onStatus: (status: ConnectionStatus) => void
}

const MAX_BACKOFF_MS = 5000

/** Game WebSocket with automatic reconnect and exponential backoff. */
export class GameSocket {
  private ws: WebSocket | null = null
  private backoff = 250
  private closed = false
  private retryTimer: ReturnType<typeof setTimeout> | undefined
  private readonly handlers: Handlers

  constructor(handlers: Handlers) {
    this.handlers = handlers
    this.connect()
  }

  send(msg: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  close(): void {
    this.closed = true
    clearTimeout(this.retryTimer)
    this.ws?.close()
  }

  private connect(): void {
    this.handlers.onStatus('connecting')
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${location.host}/ws/game`)
    this.ws = ws

    ws.onopen = () => {
      this.backoff = 250
      this.handlers.onStatus('online')
      this.handlers.onOpen()
    }
    ws.onmessage = (event) => {
      this.handlers.onMessage(JSON.parse(event.data) as ServerMessage)
    }
    ws.onclose = () => {
      this.handlers.onStatus('offline')
      if (this.closed) return
      this.retryTimer = setTimeout(() => this.connect(), this.backoff)
      this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS)
    }
  }
}
