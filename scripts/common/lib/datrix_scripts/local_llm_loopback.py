"""A real Ollama server shape on loopback, for the checks of every local-model caller.

Every gate, self-test and hook test that exercises a caller of ``datrix_scripts.local_llm``
needs a model server it controls: one on a known port that says which models it holds and
records what it was asked. This module is that server -- a real HTTP server on an ephemeral
loopback port answering the part of Ollama's API the pool uses -- so no check contacts the
network's model servers and none carries its own copy.

``LoopbackJsonServer`` answers every request through a function the check supplies, for
checks of the pool's own survey logic. ``LoopbackOllama`` builds the usual case on it: every
model it lists is loaded, and a chat is answered by ``answer``:

    GET  /api/tags      every model, with ``capabilities``
    GET  /api/ps        every model (all of them are held in memory), each with the
                        ``expires_at`` the check chose (30 minutes out by default)
    POST /api/generate  a load (no prompt): recorded in ``loads``, always succeeds
    POST /api/chat      recorded in ``chats``; HTTP 500 for a model in ``failing``,
                        otherwise ``answer(chat)`` after ``chat_seconds``
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from datrix_scripts.local_llm import LocalLlmSettings

LOOPBACK = "127.0.0.1"
DEFAULT_MODEL = "gate-model"
COMPLETION_CAPABILITIES: tuple[str, ...] = ("completion",)

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500
#: How long a check waits on its loopback server: a reachability probe, then an answer.
LOOPBACK_REACHABLE_TIMEOUT_MS = 2000
LOOPBACK_GENERATE_TIMEOUT_MS = 5000

# (method, path, JSON body or None) -> (HTTP status, JSON payload)
JsonResponder = Callable[[str, str, "dict[str, object] | None"], "tuple[int, object]"]


def closed_port() -> int:
    """A loopback port nothing listens on: bound, read, released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK, 0))
        return int(sock.getsockname()[1])


class LoopbackJsonServer:
    """A real HTTP server on an ephemeral loopback port; ``respond`` decides every answer.

    Every request is recorded so a check can assert what the client actually sent. Use it as
    a context manager: it serves from ``__enter__`` until ``__exit__``.
    """

    def __init__(self, respond: JsonResponder) -> None:
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []
        recorder = self.requests

        class _Handler(BaseHTTPRequestHandler):
            def _answer(self, method: str) -> None:
                length = int(self.headers["Content-Length"]) if "Content-Length" in self.headers else 0
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else None
                recorder.append((method, self.path, body))
                status, payload = respond(method, self.path, body)
                data = json.dumps(payload).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except ConnectionError:
                    # The client's timeout ran out before the answer: a check of that gives up on purpose.
                    return

            def do_GET(self) -> None:  # noqa: N802 -- http.server's dispatch name
                self._answer("GET")

            def do_POST(self) -> None:  # noqa: N802 -- http.server's dispatch name
                self._answer("POST")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self._httpd = ThreadingHTTPServer((LOOPBACK, 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> LoopbackJsonServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def posts_to(self, path: str) -> list[dict[str, object]]:
        """The JSON bodies POSTed to ``path``, in arrival order."""
        return [body for method, p, body in self.requests if method == "POST" and p == path and body is not None]


@dataclass(frozen=True)
class Chat:
    """One ``/api/chat`` request as the server received it."""

    model: str
    system: str
    user: str
    body: dict[str, object] = field(compare=False, hash=False)


ChatAnswer = Callable[[Chat], str]

#: What ``/api/ps`` reports as a model's ``expires_at``: RFC 3339 text with a UTC offset,
#: or ``None`` for an entry that states none.
ExpiryText = Callable[[], "str | None"]

DEFAULT_RESIDENCY = timedelta(minutes=30)


def held_for_thirty_minutes() -> str:
    """An ``expires_at`` of ``DEFAULT_RESIDENCY`` from now, as Ollama writes it."""
    return (datetime.now(UTC) + DEFAULT_RESIDENCY).isoformat()


def held_for(residency: timedelta) -> ExpiryText:
    """An ``expires_at`` source reporting every model held for *residency* from now."""
    return lambda: (datetime.now(UTC) + residency).isoformat()


def without_expiry() -> None:
    """An ``expires_at`` source for a response whose entries state none."""
    return None


def answering(text: str) -> ChatAnswer:
    """An ``answer`` that gives ``text`` to every chat."""
    return lambda _chat: text


def _chat(body: dict[str, object]) -> Chat:
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"an /api/chat body must carry a non-empty 'messages' list; got {body!r}")
    contents = [str(message["content"]) for message in messages if isinstance(message, dict)]
    return Chat(model=str(body["model"]), system=contents[0], user=contents[-1], body=body)


class LoopbackOllama(LoopbackJsonServer):
    """An Ollama server on loopback holding ``models`` in memory and answering with ``answer``."""

    def __init__(
        self,
        answer: ChatAnswer,
        models: tuple[str, ...] = (DEFAULT_MODEL,),
        *,
        failing: frozenset[str] = frozenset(),
        chat_seconds: float = 0.0,
        capabilities: tuple[str, ...] = COMPLETION_CAPABILITIES,
        expires_at: ExpiryText = held_for_thirty_minutes,
        context_length: int | None = None,
    ) -> None:
        # The context window the models are held with, as /api/ps states it; None when the server states none.
        # A load or a chat that names a window (options.num_ctx) sets it; an unload clears it.
        self.context_length = context_length
        self.chats: list[Chat] = []
        self.loads: list[str] = []
        # The body of every /api/generate request (a load, a renewal or an unload), in order.
        self.generate_bodies: list[dict[str, object]] = []
        self._answer = answer
        self._models = models
        self._failing = failing
        self._chat_seconds = chat_seconds
        self._capabilities = capabilities
        self._expires_at = expires_at
        super().__init__(self._respond)

    def __enter__(self) -> LoopbackOllama:
        super().__enter__()
        return self

    def settings(self, caller: str) -> LocalLlmSettings:
        """Pool settings that reach this server alone, offering only the models it holds, recorded as *caller*."""
        return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=LOOPBACK_REACHABLE_TIMEOUT_MS,
                                generate_timeout_ms=LOOPBACK_GENERATE_TIMEOUT_MS, allow_load=False,
                                ollama_port=self.port, caller=caller)

    def chats_for(self, model: str) -> list[Chat]:
        """The chats sent to ``model``, answered or failed."""
        return [chat for chat in self.chats if chat.model == model]

    def _resident_entry(self, model: str) -> dict[str, object]:
        """One ``/api/ps`` entry: the model, and when Ollama will unload it unless unstated."""
        expiry = self._expires_at()
        entry: dict[str, object] = {"name": model} if expiry is None else {"name": model, "expires_at": expiry}
        if self.context_length is not None:
            entry["context_length"] = self.context_length
        return entry

    def _note_window(self, body: dict[str, object]) -> None:
        """Hold the models at the window a load or chat names, or at none after an unload."""
        if body.get("keep_alive") == 0:
            self.context_length = None
            return
        options = body.get("options")
        if isinstance(options, dict) and isinstance(options.get("num_ctx"), int):
            self.context_length = options["num_ctx"]

    def _respond(self, method: str, path: str, body: dict[str, object] | None) -> tuple[int, object]:
        if method == "GET" and path == "/api/tags":
            return HTTP_OK, {"models": [{"name": m, "capabilities": list(self._capabilities)} for m in self._models]}
        if method == "GET" and path == "/api/ps":
            return HTTP_OK, {"models": [self._resident_entry(m) for m in self._models]}
        if method == "POST" and path == "/api/generate" and body is not None:
            self.loads.append(str(body["model"]))
            self.generate_bodies.append(body)
            self._note_window(body)
            return HTTP_OK, {"model": body["model"], "done": True}
        if method == "POST" and path == "/api/chat" and body is not None:
            self._note_window(body)
            return self._respond_to_chat(_chat(body))
        return HTTP_NOT_FOUND, {"error": f"{method} {path} is not part of the loopback Ollama API"}

    def _respond_to_chat(self, chat: Chat) -> tuple[int, object]:
        self.chats.append(chat)
        if chat.model in self._failing:
            return HTTP_SERVER_ERROR, {"error": f"model '{chat.model}' failed on purpose"}
        time.sleep(self._chat_seconds)
        return HTTP_OK, {"model": chat.model, "message": {"role": "assistant", "content": self._answer(chat)},
                         "done": True}
