"""The LLM port and its backends (M6, WP-6.1).

This module is the **one canonical home** of the :class:`LLMClient` Protocol
and the deterministic :class:`MockLLMClient` (the M5 strategy generator
re-exports them from here — there are no duplicate ports, I7).

Backends, resolved by :func:`get_llm_client` in strict priority order:

1. **Claude** (:class:`ClaudeClient`, lazy ``anthropic``) when
   ``ANTHROPIC_API_KEY`` is set — the primary paid backend.
2. **OpenRouter** (:class:`OpenRouterClient`, OpenAI-compatible HTTP via the
   standard library) when ``OPENROUTER_API_KEY`` is set.
3. **Ollama** (:class:`OllamaClient`, local HTTP, **no key needed**) when a
   server answers at ``QUANTOS_OLLAMA_URL`` (default
   ``http://localhost:11434``) — the free default for key-less users.
4. **Mock** (:class:`MockLLMClient`, deterministic, offline) otherwise — and
   always in tests (I6/I8).

No secret ever lives in code: keys and URLs come only from the environment.
:class:`TracingLLMClient` adds optional Langfuse tracing, lazily imported and
never required.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import socket
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

import numpy as np

from quantos.config import Settings

__all__ = [
    "ClaudeClient",
    "LLMClient",
    "LLMClientError",
    "MockLLMClient",
    "OllamaClient",
    "OpenRouterClient",
    "TracingLLMClient",
    "get_llm_client",
    "ollama_reachable",
]


class LLMClientError(RuntimeError):
    """Raised when a real backend cannot complete (missing dep, HTTP failure).

    Callers that must stay honest (the LLM analyst, I3) catch this and
    abstain — an LLM failure never fabricates conviction.
    """


@runtime_checkable
class LLMClient(Protocol):
    """The LLM port every AI-facing module depends on (I7).

    Implementations return the raw completion text; when ``schema`` is given
    the caller expects parseable JSON of that shape (callers validate — a
    malformed response is the caller's abstention path, never repaired
    silently).
    """

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        """Return the model's completion for ``prompt`` (JSON when asked)."""
        ...


# ---------------------------------------------------------------------------
# The deterministic offline backend (the only one tests ever use, I6)
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Deterministic offline stand-in for an LLM (I6/I8).

    Dispatches on the prompt type and answers with exactly the shape the
    real backends are asked for:

    - **strategy generation** prompts (M5): a JSON array of strategy specs
      drawn from the same grammar as ``RandomStrategyGenerator`` (seeded by
      the constructor), each with a stated rationale;
    - **challenger** prompts (M6): a JSON challenge that disputes any
      non-FLAT provisional decision with opposite-signed counter-evidence;
    - **analyst** prompts (M6): a JSON opinion (direction, confidence,
      evidence) derived deterministically from the prompt digest — a
      content-free stand-in whose honesty comes from the analyst's strict
      validation, not from the mock;
    - anything else: a deterministic JSON echo.

    Same ``(seed, prompt)`` in, same text out — committee decisions built on
    the mock replay bit-for-bit (I8).
    """

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.calls: list[str] = []

    # -- deterministic prompt-derived randomness ---------------------------

    def _rng(self, prompt: str) -> np.random.Generator:
        """A generator seeded by (constructor seed, prompt digest) — stable
        across processes (sha256, never the salted builtin ``hash``)."""
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).digest()
        return np.random.default_rng(int.from_bytes(digest[:8], "big"))

    # -- per-prompt-type answers -------------------------------------------

    def _generation(self, prompt: str) -> str:
        """A JSON array of validated strategy specs (the M5 contract)."""
        # Lazy import: strategy.generator re-exports this class (no cycle).
        from quantos.strategy.generator import RandomStrategyGenerator

        n = 8
        for token in prompt.replace("=", " ").split():
            if token.isdigit():
                n = int(token)
                break
        proposals = RandomStrategyGenerator(version="llm-mock-1").generate(
            n, seed=self.seed, diversity=0.0
        )
        payload = []
        for spec in proposals:
            record = spec.as_dict()
            record["rationale"] = f"proposed by mock LLM: {spec.rationale}"
            payload.append(record)
        return json.dumps(payload)

    def _challenge(self, prompt: str) -> str:
        """A JSON challenge: dispute any non-FLAT provisional decision."""
        match = re.search(r"provisional decision:\s*(LONG|SHORT|FLAT)", prompt)
        direction = match.group(1) if match else "FLAT"
        if direction == "FLAT":
            return json.dumps(
                {
                    "agrees": True,
                    "material": False,
                    "argument": "mock challenger: nothing to contest in a FLAT stance",
                    "counter_evidence": [],
                }
            )
        sign = 1.0 if direction == "LONG" else -1.0
        counter = {
            "name": "mock_counter",
            "detail": f"deterministic mock counter-argument against {direction}",
            "impact": -sign * 0.5,
            "value": None,
        }
        return json.dumps(
            {
                "agrees": False,
                "material": True,
                "argument": f"mock challenger: the case against {direction} deserves a re-debate",
                "counter_evidence": [counter],
            }
        )

    def _opinion(self, prompt: str) -> str:
        """A valid JSON analyst opinion derived from the prompt digest."""
        rng = self._rng(prompt)
        direction = ("LONG", "SHORT", "FLAT")[int(rng.integers(3))]
        sign = {"LONG": 1.0, "SHORT": -1.0, "FLAT": 0.0}[direction]
        confidence = round(
            float(rng.uniform(0.35, 0.75)) if sign else float(rng.uniform(0.05, 0.20)), 4
        )
        evidence = [
            {
                "name": f"mock_signal_{i}",
                "detail": f"deterministic mock evidence #{i} supporting {direction}",
                "impact": round(sign * float(rng.uniform(0.2, 0.8)), 4),
                "value": round(float(rng.uniform(-2.0, 2.0)), 4),
            }
            for i in range(2)
        ]
        return json.dumps(
            {
                "direction": direction,
                "confidence": confidence,
                "abstain": False,
                "evidence": evidence,
                "rationale": "deterministic mock analysis (offline stand-in)",
            }
        )

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        """Answer deterministically according to the recognised prompt type."""
        self.calls.append(prompt)
        lowered = prompt.lower()
        if "devil's advocate" in lowered:
            return self._challenge(prompt)
        if "propose" in lowered and "spec" in lowered:
            return self._generation(prompt)
        if "analyst" in lowered:
            return self._opinion(prompt)
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).hexdigest()
        return json.dumps({"response": "mock completion", "prompt_sha256": digest[:16]})


# ---------------------------------------------------------------------------
# Real backends — all optional, all lazy, keys only via env (I6)
# ---------------------------------------------------------------------------


def _json_instruction(prompt: str, schema: dict[str, Any] | None) -> str:
    """Append a strict-JSON instruction when the caller expects a schema."""
    if schema is None:
        return prompt
    return (
        f"{prompt}\n\nRespond with ONLY valid JSON matching this schema "
        f"(no prose, no code fences): {json.dumps(schema)}"
    )


class ClaudeClient:
    """Anthropic Claude adapter (priority 1). Lazy ``anthropic`` import.

    The API key is **never** stored by quantos: when ``api_key`` is omitted
    the SDK reads ``ANTHROPIC_API_KEY`` from the environment itself.
    """

    DEFAULT_MODEL = "claude-sonnet-4-5"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.timeout = timeout

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        """Complete via the Anthropic Messages API.

        Raises:
            LLMClientError: when the ``anthropic`` package is missing or the
                call fails — callers abstain, they never fabricate (I3).
        """
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised offline
            raise LLMClientError(
                "ClaudeClient needs the 'anthropic' package (pip install 'quantos[llm]')"
            ) from exc
        try:
            kwargs: dict[str, Any] = {"timeout": self.timeout}
            if self.api_key is not None:
                kwargs["api_key"] = self.api_key
            client = anthropic.Anthropic(**kwargs)
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": _json_instruction(prompt, schema)}],
            )
            return "".join(
                block.text for block in message.content if getattr(block, "type", "") == "text"
            )
        except LLMClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - any SDK/transport failure abstains upstream
            raise LLMClientError(f"Claude completion failed: {exc}") from exc


class OpenRouterClient:
    """OpenRouter adapter (priority 2): OpenAI-compatible chat completions.

    Speaks plain HTTP via the standard library — no third-party dependency
    at all. The key comes from the caller/env, never from code.
    """

    DEFAULT_MODEL = "openrouter/auto"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        """Complete via ``POST {base_url}/chat/completions``.

        Raises:
            LLMClientError: on any HTTP/parse failure.
        """
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": _json_instruction(prompt, schema)}],
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
            return str(payload["choices"][0]["message"]["content"])
        except Exception as exc:  # noqa: BLE001 - any transport failure abstains upstream
            raise LLMClientError(f"OpenRouter completion failed: {exc}") from exc


class OllamaClient:
    """Local Ollama adapter (priority 3) — the free, key-less backend.

    Talks plain HTTP to a locally-running Ollama server
    (``QUANTOS_OLLAMA_URL``, default ``http://localhost:11434``). This is
    the default real backend for users without a paid API key.
    """

    DEFAULT_MODEL = "llama3.2"
    DEFAULT_URL = "http://localhost:11434"

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.url = (url or self.DEFAULT_URL).rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        """Complete via ``POST {url}/api/generate`` (``format: json`` when a
        schema is expected).

        Raises:
            LLMClientError: when the server is unreachable or answers badly.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": _json_instruction(prompt, schema),
            "stream": False,
        }
        if schema is not None:
            payload["format"] = "json"
        request = urllib.request.Request(
            f"{self.url}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                answer = json.loads(response.read().decode())
            return str(answer["response"])
        except Exception as exc:  # noqa: BLE001 - any transport failure abstains upstream
            raise LLMClientError(f"Ollama completion failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Optional tracing (Langfuse) — lazy, never required
# ---------------------------------------------------------------------------


class TracingLLMClient:
    """Wraps any :class:`LLMClient` with best-effort call tracing.

    The tracer defaults to a lazily-imported Langfuse client (configured via
    its own ``LANGFUSE_*`` env variables); when the package is absent or the
    tracer fails, the wrapper silently degrades to a pass-through — tracing
    can never break research (I6).
    """

    def __init__(
        self,
        inner: LLMClient,
        tracer: Callable[[str, str], None] | None = None,
    ) -> None:
        """
        Args:
            inner: the wrapped backend.
            tracer: ``tracer(prompt, completion)`` callback; a lazy Langfuse
                emitter is attempted when omitted.
        """
        self.inner = inner
        self._tracer = tracer
        self._resolved = tracer is not None

    def _resolve_tracer(self) -> Callable[[str, str], None] | None:
        """Build the Langfuse emitter once, lazily; None when unavailable."""
        if self._resolved:
            return self._tracer
        self._resolved = True
        try:  # pragma: no cover - langfuse is never installed in the suite
            from langfuse import Langfuse

            langfuse = Langfuse()

            def emit(prompt: str, completion: str) -> None:
                langfuse.trace(name="quantos-llm-call").generation(
                    name=type(self.inner).__name__, input=prompt, output=completion
                )

            self._tracer = emit
        except Exception:  # noqa: BLE001 - tracing is strictly optional
            self._tracer = None
        return self._tracer

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        """Complete via the wrapped backend, then trace on a best-effort basis."""
        completion = self.inner.complete(prompt, schema=schema)
        tracer = self._resolve_tracer()
        if tracer is not None:
            # Tracing failures never surface into research.
            with contextlib.suppress(Exception):
                tracer(prompt, completion)
        return completion


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------


def ollama_reachable(url: str, timeout: float = 0.25) -> bool:
    """True when a TCP listener answers at the Ollama URL's host:port.

    A plain socket probe (no HTTP, no proxy) so an absent local server is
    detected in milliseconds and the factory can fall through to the mock.
    """
    parsed = urlparse(url if "//" in url else f"//{url}")
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 11434)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_llm_client(
    settings: Settings | None = None,
    env: Mapping[str, str] | None = None,
    probe: Callable[[str], bool] | None = None,
) -> LLMClient:
    """Resolve the best available LLM backend (Claude ▸ OpenRouter ▸ Ollama ▸ Mock).

    Args:
        settings: platform settings; built from ``env`` when omitted (so
            ``QUANTOS_LLM_BACKEND``/``QUANTOS_OLLAMA_URL``/... apply).
        env: environment mapping (``os.environ`` by default) — the only place
            API keys are ever read from (I6).
        probe: reachability check for Ollama (:func:`ollama_reachable` by
            default); injectable so tests stay fully offline.

    Returns:
        The resolved client. ``settings.llm_backend`` forces a specific
        backend (``claude``/``openrouter``/``ollama``/``mock``); ``auto``
        walks the priority order and always terminates at the deterministic
        :class:`MockLLMClient` — research never requires a key (I6). When
        Langfuse keys are present the client is wrapped in
        :class:`TracingLLMClient` (lazy, optional).
    """
    settings = settings or Settings.from_env(env)
    source: Mapping[str, str] = os.environ if env is None else env
    check = probe if probe is not None else ollama_reachable
    model = settings.llm_model or None
    timeout = settings.llm_timeout
    ollama_url = settings.ollama_url

    backend = settings.llm_backend.lower().strip() or "auto"
    client: LLMClient
    if backend == "mock":
        client = MockLLMClient(seed=settings.seed)
    elif backend == "claude":
        client = ClaudeClient(api_key=source.get("ANTHROPIC_API_KEY"), model=model, timeout=timeout)
    elif backend == "openrouter":
        client = OpenRouterClient(
            api_key=source.get("OPENROUTER_API_KEY", ""), model=model, timeout=timeout
        )
    elif backend == "ollama":
        client = OllamaClient(url=ollama_url, model=model, timeout=timeout)
    elif backend == "auto":
        if source.get("ANTHROPIC_API_KEY"):
            client = ClaudeClient(
                api_key=source.get("ANTHROPIC_API_KEY"), model=model, timeout=timeout
            )
        elif source.get("OPENROUTER_API_KEY"):
            client = OpenRouterClient(
                api_key=source["OPENROUTER_API_KEY"], model=model, timeout=timeout
            )
        elif check(ollama_url):
            client = OllamaClient(url=ollama_url, model=model, timeout=timeout)
        else:
            client = MockLLMClient(seed=settings.seed)
    else:
        raise ValueError(
            f"unknown llm_backend {settings.llm_backend!r} "
            "(expected auto|claude|openrouter|ollama|mock)"
        )

    if source.get("LANGFUSE_PUBLIC_KEY") and source.get("LANGFUSE_SECRET_KEY"):
        return TracingLLMClient(client)
    return client
