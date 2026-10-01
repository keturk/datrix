"""Local model servers on the network: discovery, readiness, load spreading, and failover.

Every script, hook and MCP tool that asks a local model for text goes through this module,
so every one of them searches the same machines, prefers the same models, spreads its
requests the same way, hands over to the next server the same way when one fails, and is
recorded in the same usage log (``shared.local_llm_usage``).

WHY DISCOVERY RATHER THAN A CONFIGURED URL
    What each machine runs changes: a llama-server container once took over the T5820's
    GPU, leaving a pinned Ollama URL and model nowhere to load, and every script pinned
    to that one URL went silent while two other machines sat idle. So each machine is
    searched for an Ollama server (port 11434) and OpenAI-compatible servers (vLLM on
    8000, llama-server on 8080 and 8081), and what they serve is discovered on every run.

CANDIDATE ORDER
    Models already in memory on any machine come first, in machine order; models Ollama
    would have to load come last, because a load claims most of a GPU. No load is offered
    on a machine where an OpenAI-compatible server answered: that server holds the GPU
    memory the load would need. When a caller names preferred models, only those are
    candidates, in the caller's order.

LOAD SPREADING
    Every resident candidate of the best preference rank is eligible, not only the first:
    a request goes to an idle ready candidate, and when every ready one is busy and another
    eligible one has not been readied yet, that one is readied and takes the request. A bulk
    run (2,400 module summaries) therefore keeps every machine's resident model busy instead
    of queueing on one while the others sit idle. A single request -- a hook's -- still
    readies and uses only the first candidate. Models Ollama would have to LOAD are never
    spread over: one is loaded only when no resident candidate is left, one at a time.

FAILOVER
    A candidate is readied before it is handed a request, and a candidate that fails -- to
    load, to answer, or mid-run -- is dropped for the rest of the run and the remaining ones
    take over. When none is left the pool raises ``LocalLlmUnavailable``; it never answers
    with nothing.

USAGE LOG
    Every request -- answered, failed, or refused because no server could serve -- is one
    line in ``LocalLlmSettings.usage_log``, labelled with ``LocalLlmSettings.caller``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from shared.local_llm_usage import (
    OUTCOME_FAILED,
    OUTCOME_OK,
    OUTCOME_UNAVAILABLE,
    UsageEntry,
    default_usage_log,
    invoking_script,
    record_usage,
)

# The HTTP APIs a local model server can speak. "ollama" is Ollama's native API, which can
# list, report and load models. "openai" is the OpenAI-compatible chat API that vLLM,
# llama.cpp's llama-server and most other inference servers expose; such a server holds
# its models resident already.
LOCAL_API_OLLAMA = "ollama"
LOCAL_API_OPENAI = "openai"

# Machines searched for local model servers, in preference order.
DEFAULT_LOCAL_MACHINES: tuple[str, ...] = (
    "10.94.0.100",  # Dell T5820, RTX 3090
    "10.94.0.101",  # Dell T7920, RTX 3090
    "10.94.0.102",  # ASUS GX10, vLLM
)

# Where the servers listen: Ollama on its fixed port, OpenAI-compatible servers on the
# ports vLLM (8000) and llama-server (8080, and 8081 beside another server) use.
OLLAMA_PORT = 11434
OPENAI_COMPATIBLE_PORTS: tuple[int, ...] = (8000, 8080, 8081)

# Models Ollama may be asked to LOAD when a machine has nothing resident and the caller
# named no model, best first. Only models installed on the machine count.
# qwen3.6:35b is the model the T7920 (10.94.0.101) has installed; without it there, that
# machine could never serve, because nothing else on it is loadable.
OLLAMA_LOAD_PREFERENCE: tuple[str, ...] = ("qwen3-coder:30b-ctx32k", "qwen3.6:35b")

# Ollama capability a model needs to answer a prompt; an embedding model lacks it.
OLLAMA_COMPLETION_CAPABILITY = "completion"

# Ollama capability that means the model reasons before answering. ``think`` is sent to
# such a model only: sending it to a model WITHOUT the capability is an error in Ollama.
OLLAMA_THINKING_CAPABILITY = "thinking"

# Ollama resolves an untagged model name to this tag.
OLLAMA_DEFAULT_TAG = "latest"

# Output tokens for the readiness request an OpenAI-compatible server is sent before it
# is handed work. One token proves the engine answers; listing a model does not (vLLM
# keeps listing its model after its engine has died).
READINESS_MAX_TOKENS = 1

# How long Ollama keeps a model loaded after a request. Requests in one run can be
# minutes apart, and a cold reload of a 20+ GB model costs minutes on a slow disk.
DEFAULT_KEEP_ALIVE = "30m"

DEFAULT_REACHABLE_TIMEOUT_MS = 3000
DEFAULT_LOAD_TIMEOUT_MS = 900000
DEFAULT_GENERATE_TIMEOUT_MS = 180000

MILLISECONDS_PER_SECOND = 1000

# A reasoning model can emit its reasoning inline even when asked not to reason.
THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)
THINK_CLOSE_TAG = "</think>"

# Name of the schema an OpenAI-compatible server is told to constrain output to.
RESPONSE_SCHEMA_NAME = "response"


class LocalLlmError(RuntimeError):
    """One local server failed one request; the pool fails over on it."""


class LocalLlmUnavailable(RuntimeError):
    """No local server can serve: none answered, or every one that did has failed."""


@dataclass(frozen=True)
class LocalHost:
    """One local model server and one model it can run: the API, where it is, the model."""

    api: str
    base_url: str
    model: str

    def label(self) -> str:
        return f"{self.api} model '{self.model}' at {self.base_url}"


@dataclass(frozen=True)
class LocalCandidate:
    """A discovered server/model pair that may be asked for text."""

    host: LocalHost
    thinking: bool
    # Already in memory -- an OpenAI-compatible server's model, or one Ollama has
    # loaded -- as opposed to a model Ollama would have to load first.
    resident: bool


@dataclass(frozen=True)
class ServerSurvey:
    """What one model server on one machine offers."""

    api: str
    base_url: str
    candidates: tuple[LocalCandidate, ...]

    def summary(self) -> str:
        resident = [c.host.model for c in self.candidates if c.resident]
        loadable = [c.host.model for c in self.candidates if not c.resident]
        parts = [f"resident {', '.join(resident) or 'none'}"]
        if loadable:
            parts.append(f"loadable {', '.join(loadable)}")
        return f"{self.api} at {self.base_url} ({'; '.join(parts)})"


@dataclass(frozen=True)
class LocalLlmSettings:
    """Where to search and how long to wait.

    ``models`` empty means any resident model, then ``OLLAMA_LOAD_PREFERENCE`` for a
    load. Non-empty means only those models, in that order, resident or loadable.
    """

    machines: tuple[str, ...] = DEFAULT_LOCAL_MACHINES
    models: tuple[str, ...] = ()
    reachable_timeout_ms: int = DEFAULT_REACHABLE_TIMEOUT_MS
    load_timeout_ms: int = DEFAULT_LOAD_TIMEOUT_MS
    generate_timeout_ms: int = DEFAULT_GENERATE_TIMEOUT_MS
    keep_alive: str = DEFAULT_KEEP_ALIVE
    # False offers only models already in memory: a caller that must answer within
    # seconds (a Claude Code hook) can never wait out a multi-minute Ollama load.
    allow_load: bool = True
    # Where servers listen on each machine. The standard ports; a test points these at
    # servers it started itself.
    ollama_port: int = OLLAMA_PORT
    openai_ports: tuple[int, ...] = OPENAI_COMPATIBLE_PORTS
    # Where every request is recorded, and the name it is recorded under: the running
    # script's name unless the caller says otherwise (a hook, an MCP tool).
    usage_log: Path = field(default_factory=default_usage_log)
    caller: str = field(default_factory=invoking_script)


@dataclass(frozen=True)
class ChatRequest:
    """One system + user exchange and how to sample it.

    ``max_tokens`` and ``context_window`` left unset take the server's own values;
    ``context_window`` reaches Ollama only (an OpenAI-compatible server fixes its
    context when it starts). ``json_schema`` constrains the output on both APIs.
    """

    system: str
    user: str
    temperature: float
    max_tokens: int | None = None
    context_window: int | None = None
    json_schema: dict[str, object] | None = field(default=None, hash=False)
    think: bool = False


@dataclass(frozen=True)
class LocalLlmReply:
    """A model's answer, with reasoning stripped, and the server/model that gave it."""

    text: str
    host: LocalHost


def parse_local_machine(spec: str) -> str:
    """Validate a machine value: a bare host name or IP address, nothing else.

    The ports and APIs are searched, so a scheme, port or path in the value would be
    ignored at best; it is rejected so a mistyped value never searches the wrong place.
    """
    machine = spec.strip()
    if not machine or any(sep in machine for sep in ("/", ":", "=", " ")):
        raise argparse.ArgumentTypeError(
            f"Local machine '{spec}' is not a bare host name or IP address. Pass only the "
            f"machine, e.g. {DEFAULT_LOCAL_MACHINES[0]}; its Ollama port {OLLAMA_PORT} and "
            f"OpenAI-compatible ports {', '.join(map(str, OPENAI_COMPATIBLE_PORTS))} are searched."
        )
    return machine


def qualified_ollama_model(model: str) -> str:
    """Return the model name as Ollama lists it, with the implicit tag made explicit."""
    return model if ":" in model else f"{model}:{OLLAMA_DEFAULT_TAG}"


def listed_ollama_models(tags_response: object) -> dict[str, frozenset[str]]:
    """Map each model name in an Ollama ``/api/tags`` response to its capabilities."""
    if not isinstance(tags_response, dict) or not isinstance(tags_response.get("models"), list):
        raise ValueError("expected a JSON object with a 'models' list")
    models: dict[str, frozenset[str]] = {}
    for entry in tags_response["models"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        capabilities = entry.get("capabilities")
        listed = capabilities if isinstance(capabilities, list) else []
        models[entry["name"]] = frozenset(str(capability) for capability in listed)
    return models


def loaded_ollama_models(ps_response: object) -> list[str]:
    """The model names in an Ollama ``/api/ps`` response -- the models it holds in memory."""
    if not isinstance(ps_response, dict) or not isinstance(ps_response.get("models"), list):
        raise ValueError("expected a JSON object with a 'models' list")
    return [
        entry["name"]
        for entry in ps_response["models"]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]


def listed_openai_models(models_response: object) -> list[str]:
    """The served model ids, in listed order, from an OpenAI-compatible ``/v1/models`` response."""
    if not isinstance(models_response, dict) or not isinstance(models_response.get("data"), list):
        raise ValueError("expected a JSON object with a 'data' list")
    return [
        entry["id"]
        for entry in models_response["data"]
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]


def strip_reasoning(text: str) -> str:
    """Remove inline reasoning: whole ``<think>`` blocks, then anything before a stray close tag."""
    cleaned = THINK_BLOCK_PATTERN.sub("", text)
    if THINK_CLOSE_TAG in cleaned:
        cleaned = cleaned.rsplit(THINK_CLOSE_TAG, 1)[1]
    return cleaned.strip()


def _fetch_json(uri: str, timeout_ms: int) -> object:
    with urllib.request.urlopen(uri, timeout=max(1, timeout_ms / MILLISECONDS_PER_SECOND)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wanted(models: tuple[str, ...], api: str) -> tuple[str, ...]:
    """The caller's model names in the form ``api`` lists them."""
    if api == LOCAL_API_OLLAMA:
        return tuple(qualified_ollama_model(m) for m in models)
    return models


def survey_ollama(base_url: str, settings: LocalLlmSettings) -> ServerSurvey:
    """List what an Ollama server can answer with: its loaded models, then loadable ones.

    A loaded model costs nothing to use. A model that must be loaded is offered only if
    it is wanted (the caller's models, else ``OLLAMA_LOAD_PREFERENCE``) and installed
    here; whether it fits the GPU is learned by loading it. Raises OSError or ValueError
    when nothing usable answers.
    """
    capabilities = listed_ollama_models(_fetch_json(f"{base_url}/api/tags", settings.reachable_timeout_ms))
    loaded = loaded_ollama_models(_fetch_json(f"{base_url}/api/ps", settings.reachable_timeout_ms))
    wanted = _wanted(settings.models, LOCAL_API_OLLAMA)

    def candidate(model: str, resident: bool) -> LocalCandidate:
        thinking = OLLAMA_THINKING_CAPABILITY in capabilities[model]
        return LocalCandidate(LocalHost(LOCAL_API_OLLAMA, base_url, model), thinking, resident)

    answering = {model for model in capabilities if OLLAMA_COMPLETION_CAPABILITY in capabilities[model]}
    resident = [
        candidate(model, True)
        for model in loaded
        if model in answering and (not wanted or model in wanted)
    ]
    loadable_names = wanted or _wanted(OLLAMA_LOAD_PREFERENCE, LOCAL_API_OLLAMA)
    loadable = [
        candidate(model, False)
        for model in loadable_names
        if model in answering and model not in loaded
    ]
    return ServerSurvey(LOCAL_API_OLLAMA, base_url, tuple(resident + loadable))


def survey_openai(base_url: str, settings: LocalLlmSettings) -> ServerSurvey:
    """List the models an OpenAI-compatible server serves; each is resident by definition.

    Such a server does not say whether a model reasons, so every request states the
    caller's ``think`` choice through the chat template. Raises OSError or ValueError
    when nothing usable answers.
    """
    served = listed_openai_models(_fetch_json(f"{base_url}/v1/models", settings.reachable_timeout_ms))
    wanted = _wanted(settings.models, LOCAL_API_OPENAI)
    models = [m for m in served if not wanted or m in wanted]
    return ServerSurvey(
        LOCAL_API_OPENAI,
        base_url,
        tuple(LocalCandidate(LocalHost(LOCAL_API_OPENAI, base_url, m), False, True) for m in models),
    )


Surveyor = Callable[[str, LocalLlmSettings], ServerSurvey]


def machine_endpoints(machine: str, settings: LocalLlmSettings) -> list[tuple[Surveyor, str]]:
    """Every (surveyor, base URL) a model server on ``machine`` may listen at."""
    endpoints: list[tuple[Surveyor, str]] = [(survey_ollama, f"http://{machine}:{settings.ollama_port}")]
    endpoints.extend((survey_openai, f"http://{machine}:{port}") for port in settings.openai_ports)
    return endpoints


def _survey_endpoint(surveyor: Surveyor, base_url: str, settings: LocalLlmSettings) -> list[ServerSurvey]:
    """Run one survey: the server found at ``base_url``, or nothing if none answered.

    A closed port, a dropped connection, a timeout, and a port serving something other
    than a model API are all normal while searching a machine, so none is an error.
    """
    try:
        return [surveyor(base_url, settings)]
    except (OSError, ValueError):
        return []


def _preference_rank(settings: LocalLlmSettings, candidate: LocalCandidate) -> int:
    wanted = _wanted(settings.models, candidate.host.api)
    return wanted.index(candidate.host.model) if candidate.host.model in wanted else 0


def discover_candidates(settings: LocalLlmSettings, report: Callable[[str], None]) -> list[LocalCandidate]:
    """Search every machine for model servers and return what they offer, best first.

    Every endpoint of every machine is surveyed in parallel, so a machine that drops
    connections costs one timeout, not one per port. Nothing is loaded here.
    """
    endpoints = [
        (machine, surveyor, base_url)
        for machine in settings.machines
        for surveyor, base_url in machine_endpoints(machine, settings)
    ]
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        surveys = list(pool.map(lambda e: _survey_endpoint(e[1], e[2], settings), endpoints))

    found: list[ServerSurvey] = []
    for machine in settings.machines:
        on_machine = [s for (m, _, _), hits in zip(endpoints, surveys) if m == machine for s in hits]
        if any(s.api == LOCAL_API_OPENAI for s in on_machine):
            on_machine = [
                ServerSurvey(s.api, s.base_url, tuple(c for c in s.candidates if c.resident))
                for s in on_machine
            ]
        if on_machine:
            report(f"Local machine {machine}: {'; '.join(s.summary() for s in on_machine)}.")
        else:
            ports = ", ".join(str(p) for p in (settings.ollama_port, *settings.openai_ports))
            report(f"Local machine {machine}: no model server answered on ports {ports}.")
        found.extend(on_machine)

    candidates = [c for survey in found for c in survey.candidates]
    resident = sorted((c for c in candidates if c.resident), key=lambda c: _preference_rank(settings, c))
    if not settings.allow_load:
        return resident
    loadable = sorted((c for c in candidates if not c.resident), key=lambda c: _preference_rank(settings, c))
    return resident + loadable


def _post_json(uri: str, body: dict[str, object], timeout_ms: int, model: str) -> dict[str, object]:
    """POST one JSON request to a local model server and return the decoded JSON object.

    Every failure is a LocalLlmError so the pool can fail over on it: URLError, a timeout,
    and a connection reset mid-read are all OSError, and an HTTP error's body carries the
    real cause (model not found, GPU out of memory) where str(exc) is only "HTTP Error 500".
    """
    req = urllib.request.Request(
        uri,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=max(1, timeout_ms / MILLISECONDS_PER_SECOND)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise LocalLlmError(
            f"Request to {uri} for model '{model}' failed with HTTP {exc.code}. "
            f"Server response: {detail or '(empty body)'}"
        ) from exc
    except OSError as exc:
        raise LocalLlmError(f"Request to {uri} for model '{model}' failed: {exc}") from exc
    except ValueError as exc:
        raise LocalLlmError(f"{uri} returned a body that is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LocalLlmError(f"{uri} returned JSON that is not an object for model '{model}'")
    return data


def _messages(request: ChatRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": request.system},
        {"role": "user", "content": request.user},
    ]


def ollama_chat_body(candidate: LocalCandidate, request: ChatRequest, keep_alive: str) -> dict[str, object]:
    """One non-streaming Ollama ``/api/chat`` request."""
    options: dict[str, object] = {"temperature": request.temperature}
    if request.max_tokens is not None:
        options["num_predict"] = request.max_tokens
    if request.context_window is not None:
        options["num_ctx"] = request.context_window
    body: dict[str, object] = {
        "model": candidate.host.model,
        "messages": _messages(request),
        "stream": False,
        "keep_alive": keep_alive,
        "options": options,
    }
    if candidate.thinking:
        body["think"] = request.think
    if request.json_schema is not None:
        body["format"] = request.json_schema
    return body


def openai_chat_body(model: str, request: ChatRequest) -> dict[str, object]:
    """One non-streaming chat request for an OpenAI-compatible server.

    Reasoning is switched through the chat template (``enable_thinking``); a server
    whose template has no such switch ignores the variable.
    """
    body: dict[str, object] = {
        "model": model,
        "messages": _messages(request),
        "temperature": request.temperature,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": request.think},
    }
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    if request.json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": RESPONSE_SCHEMA_NAME, "schema": request.json_schema},
        }
    return body


def _complete_ollama(candidate: LocalCandidate, request: ChatRequest, settings: LocalLlmSettings) -> str:
    uri = f"{candidate.host.base_url}/api/chat"
    data = _post_json(
        uri, ollama_chat_body(candidate, request, settings.keep_alive),
        settings.generate_timeout_ms, candidate.host.model,
    )
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LocalLlmError(f"{uri} returned no message content for model '{candidate.host.model}'")
    return content


def _complete_openai(candidate: LocalCandidate, request: ChatRequest, settings: LocalLlmSettings) -> str:
    uri = f"{candidate.host.base_url}/v1/chat/completions"
    data = _post_json(
        uri, openai_chat_body(candidate.host.model, request),
        settings.generate_timeout_ms, candidate.host.model,
    )
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LocalLlmError(f"{uri} returned no choices for model '{candidate.host.model}'")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LocalLlmError(
            f"{uri} returned no message content for model '{candidate.host.model}' "
            f"(finish_reason={choices[0].get('finish_reason')!r})"
        )
    return content


_COMPLETERS: dict[str, Callable[[LocalCandidate, ChatRequest, LocalLlmSettings], str]] = {
    LOCAL_API_OLLAMA: _complete_ollama,
    LOCAL_API_OPENAI: _complete_openai,
}


def complete(candidate: LocalCandidate, request: ChatRequest, settings: LocalLlmSettings) -> str:
    """Ask one candidate for an answer; return it with reasoning stripped.

    An empty answer is a failure of this candidate, not an answer: raises LocalLlmError.
    """
    text = strip_reasoning(_COMPLETERS[candidate.host.api](candidate, request, settings))
    if not text:
        raise LocalLlmError(f"{candidate.host.label()} returned an empty answer")
    return text


def ready_candidate(candidate: LocalCandidate, settings: LocalLlmSettings) -> None:
    """Prove the model answers before it is handed work; raise LocalLlmError if not.

    Ollama loads on demand: a generate request with no prompt only loads the model (or
    renews a loaded one's keep-alive). Doing that once, under the load timeout, keeps a
    cold load from being charged against a generate call's timeout, and a model that
    cannot load (out of GPU memory) is caught here. An OpenAI-compatible server is sent a
    one-token completion under the generate timeout: its model is already in memory, and
    only an answer proves its engine is alive.
    """
    host = candidate.host
    if host.api == LOCAL_API_OLLAMA:
        _post_json(
            f"{host.base_url}/api/generate",
            {"model": host.model, "keep_alive": settings.keep_alive},
            settings.load_timeout_ms,
            host.model,
        )
        return
    uri = f"{host.base_url}/v1/chat/completions"
    ping = ChatRequest(system="Reply with one word.", user="ping", temperature=0.0, max_tokens=READINESS_MAX_TOKENS)
    data = _post_json(uri, openai_chat_body(host.model, ping), settings.generate_timeout_ms, host.model)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LocalLlmError(f"{uri} answered a readiness request for model '{host.model}' with no choices")


def _report_to_stderr(line: str) -> None:
    print(line, file=sys.stderr)


class LocalLlmPool:
    """The local candidates for one run: readied lazily, spread over, and failed over.

    Safe to share between threads. Discovery runs once, under the lock. Readying a
    candidate happens outside it (a readiness check takes seconds, an Ollama load
    minutes), with the candidate marked as being readied so no second thread readies it
    too; a thread with nothing ready to use waits for that. A failed candidate is dropped
    once, however many threads fail on it.
    """

    def __init__(self, settings: LocalLlmSettings, report: Callable[[str], None] = _report_to_stderr) -> None:
        self._settings = settings
        self._report = report
        self._cond = threading.Condition()
        self._candidates: list[LocalCandidate] | None = None
        self._ready: set[LocalCandidate] = set()
        self._readying: set[LocalCandidate] = set()
        self._in_flight: dict[LocalCandidate, int] = {}
        self._last_failure = ""

    @property
    def settings(self) -> LocalLlmSettings:
        return self._settings

    def activate(self) -> LocalHost:
        """Discover (once) and ready a candidate; return it.

        Raises LocalLlmUnavailable when no candidate can serve.
        """
        candidate = self._acquire()
        self._release(candidate)
        return candidate.host

    def is_exhausted(self) -> bool:
        """True once discovery ran and every candidate has failed."""
        with self._cond:
            return self._candidates is not None and not self._candidates

    def chat(self, request: ChatRequest) -> LocalLlmReply:
        """Answer ``request`` from an eligible candidate, failing over until one answers."""
        prompt_chars = len(request.system) + len(request.user)
        while True:
            try:
                candidate = self._acquire()
            except LocalLlmUnavailable as exc:
                self._record(None, OUTCOME_UNAVAILABLE, prompt_chars, 0, 0.0, str(exc))
                raise
            started = time.perf_counter()
            try:
                text = complete(candidate, request, self._settings)
            except LocalLlmError as exc:
                self._record(candidate, OUTCOME_FAILED, prompt_chars, 0, time.perf_counter() - started, str(exc))
                self._drop(candidate, str(exc))
                continue
            finally:
                self._release(candidate)
            self._record(candidate, OUTCOME_OK, prompt_chars, len(text), time.perf_counter() - started, "")
            return LocalLlmReply(text, candidate.host)

    def _record(self, candidate: LocalCandidate | None, outcome: str, prompt_chars: int, answer_chars: int,
                seconds: float, error: str) -> None:
        host = candidate.host if candidate is not None else LocalHost("", "", "")
        record_usage(self._settings.usage_log, UsageEntry(
            caller=self._settings.caller, outcome=outcome, api=host.api, model=host.model,
            base_url=host.base_url, prompt_chars=prompt_chars, answer_chars=answer_chars,
            seconds=seconds, error=error))

    def _acquire(self) -> LocalCandidate:
        """An eligible candidate, readied, with one more request counted against it."""
        while True:
            with self._cond:
                chosen, to_ready = self._choose_locked()
                if chosen is not None:
                    self._in_flight[chosen] += 1
                    return chosen
                if to_ready is None:
                    # Another thread is readying the only eligible candidate.
                    self._cond.wait()
                    continue
                self._readying.add(to_ready)
            self._ready_outside_lock(to_ready)

    def _choose_locked(self) -> tuple[LocalCandidate | None, LocalCandidate | None]:
        """(a ready candidate to use, None) or (None, a candidate to ready) or (None, None) to wait."""
        if self._candidates is None:
            self._candidates = discover_candidates(self._settings, self._report)
        if not self._candidates:
            raise LocalLlmUnavailable(self._unavailable_message())
        eligible = self._eligible(self._candidates)
        ready =[c for c in eligible if c in self._ready]
        idle = [c for c in ready if self._in_flight[c] == 0]
        if idle:
            return idle[0], None
        unready = [c for c in eligible if c not in self._ready and c not in self._readying]
        if unready:
            return None, unready[0]
        if ready:
            return min(ready, key=lambda c: self._in_flight[c]), None
        return None, None

    def _eligible(self, candidates: list[LocalCandidate]) -> list[LocalCandidate]:
        """The candidates a request may go to: every resident one of the best preference
        rank, or -- when none is resident -- the first that would have to be loaded."""
        resident = [c for c in candidates if c.resident]
        if not resident:
            return candidates[:1]
        best = min(_preference_rank(self._settings, c) for c in resident)
        return [c for c in resident if _preference_rank(self._settings, c) == best]

    def _ready_outside_lock(self, candidate: LocalCandidate) -> None:
        self._report(self._readiness_line(candidate))
        try:
            ready_candidate(candidate, self._settings)
        except LocalLlmError as exc:
            self._report(f"Warning: {candidate.host.label()} cannot serve: {exc}")
            with self._cond:
                self._readying.discard(candidate)
                self._remove_locked(candidate, str(exc))
                self._cond.notify_all()
            return
        with self._cond:
            self._readying.discard(candidate)
            self._ready.add(candidate)
            self._in_flight[candidate] = 0
            self._cond.notify_all()
        self._report(f"Using {candidate.host.label()}.")

    def _release(self, candidate: LocalCandidate) -> None:
        with self._cond:
            if candidate in self._in_flight:
                self._in_flight[candidate] -= 1

    def _drop(self, candidate: LocalCandidate, failure: str) -> None:
        with self._cond:
            if self._candidates is not None and candidate in self._candidates:
                self._report(f"Warning: {candidate.host.label()} failed: {failure}")
            self._remove_locked(candidate, failure)
            self._cond.notify_all()

    def _remove_locked(self, candidate: LocalCandidate, failure: str) -> None:
        self._last_failure = failure
        if self._candidates is not None and candidate in self._candidates:
            self._candidates.remove(candidate)
        self._ready.discard(candidate)

    def _readiness_line(self, candidate: LocalCandidate) -> str:
        if candidate.host.api == LOCAL_API_OLLAMA:
            verb = "Checking" if candidate.resident else "Loading"
            limit_ms = self._settings.load_timeout_ms
        else:
            verb = "Checking"
            limit_ms = self._settings.generate_timeout_ms
        return f"{verb} {candidate.host.label()} (up to {limit_ms // MILLISECONDS_PER_SECOND}s)..."

    def _unavailable_message(self) -> str:
        searched = ", ".join(self._settings.machines)
        wanted = (
            f"any of the models {', '.join(self._settings.models)}"
            if self._settings.models
            else f"a resident model, or Ollama with one of {', '.join(OLLAMA_LOAD_PREFERENCE)} installed"
        )
        detail = f" Last failure: {self._last_failure}" if self._last_failure else ""
        return (
            f"No local model server could answer (searched {searched}). Start a model server "
            f"on one of those machines serving {wanted}, or pass other machines "
            f"(--local-machine).{detail}"
        )


@dataclass(frozen=True)
class AdvisoryText:
    """An advisory section's body and what produced it."""

    text: str
    # The server and model that answered, or ADVISORY_UNAVAILABLE_SOURCE.
    source: str


ADVISORY_UNAVAILABLE_SOURCE = "unavailable"


def advisory_reply(settings: LocalLlmSettings, request: ChatRequest, purpose: str) -> AdvisoryText:
    """The model's answer for an advisory report section, or a line saying why there is none.

    Advisory sections never decide pass/fail, so a missing answer is reported in the
    section itself rather than failing the run that produced the deterministic findings.
    """
    try:
        reply = LocalLlmPool(settings).chat(request)
    except LocalLlmUnavailable as exc:
        return AdvisoryText(f"{purpose} unavailable: {exc}", ADVISORY_UNAVAILABLE_SOURCE)
    return AdvisoryText(reply.text, reply.host.label())


def advisory_text(settings: LocalLlmSettings, request: ChatRequest, purpose: str) -> str:
    """``advisory_reply`` for a caller that needs only the section body."""
    return advisory_reply(settings, request, purpose).text


def add_local_llm_arguments(
    parser: argparse.ArgumentParser,
    *,
    generate_timeout_ms: int = DEFAULT_GENERATE_TIMEOUT_MS,
    model_preference: bool = True,
) -> None:
    """Add the flags every local-model script shares; read them back with ``local_llm_settings``."""
    group = parser.add_argument_group("local model servers")
    group.add_argument(
        "--local-machine",
        dest="local_machine_specs",
        action="append",
        type=parse_local_machine,
        help=(
            "A machine (host name or IP) to search for local model servers: Ollama on port "
            f"{OLLAMA_PORT}, OpenAI-compatible servers on ports "
            f"{', '.join(map(str, OPENAI_COMPATIBLE_PORTS))}. Repeat to list several, in "
            f"preference order. Default: {', '.join(DEFAULT_LOCAL_MACHINES)}."
        ),
    )
    if model_preference:
        group.add_argument(
            "--local-model",
            dest="local_models",
            action="append",
            help=(
                "Use only this model (repeat to list several, best first). Default: any "
                f"model already in memory, else load {', '.join(OLLAMA_LOAD_PREFERENCE)}."
            ),
        )
    group.add_argument(
        "--local-timeout-ms",
        type=int,
        default=generate_timeout_ms,
        help=f"Timeout for each request to a ready model (default: {generate_timeout_ms}).",
    )
    group.add_argument(
        "--local-load-timeout-ms",
        type=int,
        default=DEFAULT_LOAD_TIMEOUT_MS,
        help=(
            "Timeout for loading an Ollama model into memory before its first request. A cold "
            f"load of a large model from a slow disk takes minutes (default: {DEFAULT_LOAD_TIMEOUT_MS})."
        ),
    )
    group.add_argument(
        "--local-reachable-timeout-ms",
        type=int,
        default=DEFAULT_REACHABLE_TIMEOUT_MS,
        help=(
            "Timeout for each request that searches a machine for model servers "
            f"(default: {DEFAULT_REACHABLE_TIMEOUT_MS})."
        ),
    )
    group.add_argument(
        "--local-keep-alive",
        default=DEFAULT_KEEP_ALIVE,
        help=f"How long Ollama keeps a model loaded after a request (default: {DEFAULT_KEEP_ALIVE}).",
    )


def local_llm_settings(args: argparse.Namespace, *, models: tuple[str, ...] | None = None) -> LocalLlmSettings:
    """Build settings from ``add_local_llm_arguments`` flags.

    ``models`` is for a script that pins its model through its own flag (and so added the
    flags with ``model_preference=False``); otherwise ``--local-model`` supplies it.
    """
    specs = args.local_machine_specs or DEFAULT_LOCAL_MACHINES
    # argparse leaves an unrepeated "append" flag as None, not an empty list.
    preferred = models if models is not None else tuple(args.local_models or ())
    return LocalLlmSettings(
        # dict.fromkeys drops a repeated value while keeping the preference order.
        machines=tuple(dict.fromkeys(specs)),
        models=tuple(dict.fromkeys(preferred)),
        reachable_timeout_ms=args.local_reachable_timeout_ms,
        load_timeout_ms=args.local_load_timeout_ms,
        generate_timeout_ms=args.local_timeout_ms,
        keep_alive=args.local_keep_alive,
    )
