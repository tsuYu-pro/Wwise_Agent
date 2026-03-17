# -*- coding: utf-8 -*-
"""
Wwise Agent — API Server for UE Bridge Integration

Provides:
- HTTP REST endpoints (/api/health, /api/shutdown, /api/chat, /api/asset_sync)
- WebSocket endpoint (/ws) for full-duplex communication with UE plugin

Usage:
    python launcher.py --headless --port 8765
"""

import asyncio
import json
import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Set

logger = logging.getLogger("wwise_agent.api_server")

# ============================================================================
# Try to import aiohttp (lightweight async HTTP+WS server)
# Falls back to a simple built-in implementation if not available
# ============================================================================

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.warning("aiohttp not installed. Using fallback HTTP server. "
                    "Install aiohttp for full WebSocket support: pip install aiohttp")


class AgentAPIServer:
    """
    Lightweight API server for communication with the UE WwiseAgentBridge plugin.

    Exposes:
    - GET  /api/health          — Health check / heartbeat
    - POST /api/shutdown        — Graceful shutdown
    - POST /api/chat            — Send a chat message to the Agent
    - POST /api/asset_sync      — Trigger Wwise → UE asset sync
    - GET  /api/status          — Current Agent state
    - WS   /ws                  — Full-duplex WebSocket
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws_clients: Set[web.WebSocketResponse] = set()
        self._shutdown_event = threading.Event()

        # Callback hooks — set by the Agent main module
        self.on_chat_message = None          # async def (msg: str) -> str
        self.on_asset_sync_request = None    # async def (payload: dict) -> dict
        self.on_shutdown_request = None      # def () -> None

    # ========================================================================
    # Lifecycle
    # ========================================================================

    def start(self):
        """Start the API server in a background thread."""
        if not HAS_AIOHTTP:
            self._start_fallback()
            return

        self._thread = threading.Thread(target=self._run_aiohttp, daemon=True, name="AgentAPIServer")
        self._thread.start()
        logger.info("Agent API Server starting on %s:%d", self.host, self.port)

    def stop(self):
        """Stop the API server gracefully."""
        self._shutdown_event.set()

        if self._loop and self._runner:
            future = asyncio.run_coroutine_threadsafe(self._cleanup(), self._loop)
            try:
                future.result(timeout=5.0)
            except Exception as e:
                logger.warning("Error during API server cleanup: %s", e)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        logger.info("Agent API Server stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ========================================================================
    # WebSocket Broadcast
    # ========================================================================

    async def broadcast_ws(self, msg_type: str, payload: Dict[str, Any]):
        """Send a message to all connected WebSocket clients."""
        message = json.dumps({
            "type": msg_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        dead_clients = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead_clients.add(ws)

        self._ws_clients -= dead_clients

    def broadcast_sync(self, msg_type: str, payload: Dict[str, Any]):
        """Thread-safe synchronous wrapper for broadcast_ws."""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self.broadcast_ws(msg_type, payload), self._loop
            )

    # ========================================================================
    # aiohttp Server
    # ========================================================================

    def _run_aiohttp(self):
        """Run the aiohttp server in its own event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._setup_aiohttp())
            self._loop.run_until_complete(self._serve_forever())
        except Exception as e:
            logger.error("API server error: %s", e)
        finally:
            self._loop.close()

    async def _setup_aiohttp(self):
        self._app = web.Application()

        # Register routes
        self._app.router.add_get("/api/health", self._handle_health)
        self._app.router.add_post("/api/shutdown", self._handle_shutdown)
        self._app.router.add_post("/api/chat", self._handle_chat)
        self._app.router.add_post("/api/asset_sync", self._handle_asset_sync)
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/ws", self._handle_websocket)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        logger.info("Agent API Server listening on http://%s:%d", self.host, self.port)

    async def _serve_forever(self):
        """Serve until shutdown event is set."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(0.5)

    async def _cleanup(self):
        """Close all WebSocket connections and stop the server."""
        for ws in list(self._ws_clients):
            await ws.close()
        self._ws_clients.clear()

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    # ========================================================================
    # HTTP Handlers
    # ========================================================================

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint for UE heartbeat."""
        return web.json_response({
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": self._get_version(),
            "ws_clients": len(self._ws_clients),
        })

    async def _handle_shutdown(self, request: web.Request) -> web.Response:
        """Graceful shutdown endpoint."""
        logger.info("Shutdown requested via API.")
        if self.on_shutdown_request:
            self.on_shutdown_request()
        self._shutdown_event.set()
        return web.json_response({"status": "shutting_down"})

    async def _handle_chat(self, request: web.Request) -> web.Response:
        """Chat endpoint — receives a user message, returns Agent response."""
        try:
            body = await request.json()
            user_message = body.get("message", "")

            if not user_message:
                return web.json_response({"error": "Empty message"}, status=400)

            if self.on_chat_message:
                response_text = await self.on_chat_message(user_message)
            else:
                response_text = "[Agent not connected — no chat handler registered]"

            return web.json_response({
                "status": "ok",
                "response": response_text,
            })
        except Exception as e:
            logger.error("Chat handler error: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_asset_sync(self, request: web.Request) -> web.Response:
        """Asset sync endpoint — push Wwise changes to UE."""
        try:
            body = await request.json()

            if self.on_asset_sync_request:
                result = await self.on_asset_sync_request(body)
            else:
                result = {"status": "no_handler"}

            # Also broadcast to all WebSocket clients
            await self.broadcast_ws("asset_sync", body)

            return web.json_response(result)
        except Exception as e:
            logger.error("Asset sync handler error: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Agent status endpoint."""
        return web.json_response({
            "status": "running",
            "mode": "headless" if "--headless" in sys.argv else "gui",
            "ws_clients": len(self._ws_clients),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ========================================================================
    # WebSocket Handler
    # ========================================================================

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket endpoint for full-duplex communication with UE."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._ws_clients.add(ws)
        logger.info("WebSocket client connected. Total: %d", len(self._ws_clients))

        # Send welcome message
        await ws.send_json({
            "type": "connected",
            "payload": {
                "message": "Connected to Wwise AI Agent",
                "version": self._get_version(),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._process_ws_message(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("WebSocket error: %s", ws.exception())
        finally:
            self._ws_clients.discard(ws)
            logger.info("WebSocket client disconnected. Total: %d", len(self._ws_clients))

        return ws

    async def _process_ws_message(self, ws: web.WebSocketResponse, raw: str):
        """Process an incoming WebSocket message."""
        try:
            data = json.loads(raw)
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "chat":
                # Chat message from UE
                user_message = payload.get("message", "")
                if self.on_chat_message and user_message:
                    response_text = await self.on_chat_message(user_message)
                    await ws.send_json({
                        "type": "chat_response",
                        "payload": {"message": response_text},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            elif msg_type == "asset_sync_request":
                # Asset sync request from UE
                if self.on_asset_sync_request:
                    result = await self.on_asset_sync_request(payload)
                    await ws.send_json({
                        "type": "asset_sync_response",
                        "payload": result,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            elif msg_type == "heartbeat":
                # Respond to heartbeat
                await ws.send_json({
                    "type": "heartbeat_ack",
                    "payload": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            else:
                logger.warning("Unknown WS message type: %s", msg_type)

        except json.JSONDecodeError:
            logger.warning("Invalid JSON received via WebSocket: %s", raw[:200])
        except Exception as e:
            logger.error("Error processing WS message: %s", e)

    # ========================================================================
    # Helpers
    # ========================================================================

    def _get_version(self) -> str:
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            if version_file.exists():
                return version_file.read_text().strip()
        except Exception:
            pass
        return "unknown"

    # ========================================================================
    # Fallback (no aiohttp)
    # ========================================================================

    def _start_fallback(self):
        """Minimal HTTP server using http.server (no WebSocket support)."""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import json as _json

        server_ref = self

        class FallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                logger.debug(format, *args)

            def do_GET(self):
                if self.path == "/api/health":
                    self._respond(200, {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})
                elif self.path == "/api/status":
                    self._respond(200, {"status": "running", "mode": "fallback"})
                else:
                    self._respond(404, {"error": "Not found"})

            def do_POST(self):
                if self.path == "/api/shutdown":
                    self._respond(200, {"status": "shutting_down"})
                    server_ref._shutdown_event.set()
                else:
                    self._respond(404, {"error": "Not found"})

            def _respond(self, code, body):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(_json.dumps(body).encode("utf-8"))

        def run():
            httpd = HTTPServer((self.host, self.port), FallbackHandler)
            httpd.timeout = 1.0
            logger.info("Fallback HTTP server on %s:%d (no WebSocket)", self.host, self.port)
            while not self._shutdown_event.is_set():
                httpd.handle_request()
            httpd.server_close()

        self._thread = threading.Thread(target=run, daemon=True, name="AgentAPIServer-Fallback")
        self._thread.start()


# ============================================================================
# Headless Entry Point
# ============================================================================

def run_headless(port: int = 8765):
    """
    Run the Agent in headless (server-only) mode.
    Called from launcher.py --headless
    """
    # Ensure project root in sys.path
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    logger.info("Starting Wwise Agent in headless mode (port=%d)", port)

    server = AgentAPIServer(port=port)

    # TODO: Wire up actual Agent chat handler
    async def dummy_chat(msg: str) -> str:
        return f"[Headless Agent] Received: {msg}"

    server.on_chat_message = dummy_chat

    def handle_shutdown():
        logger.info("Shutdown signal received.")
        sys.exit(0)

    server.on_shutdown_request = handle_shutdown

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: server.stop())
    signal.signal(signal.SIGTERM, lambda *_: server.stop())

    server.start()

    # Block main thread until shutdown
    try:
        server._shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Wwise Agent API Server")
    parser.add_argument("--port", type=int, default=8765, help="Server port")
    args = parser.parse_args()
    run_headless(port=args.port)
