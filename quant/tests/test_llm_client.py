"""WP-6.1 — LLMClient port, backends and factory resolution.

Acceptance: the factory resolves Claude ▸ OpenRouter ▸ Ollama ▸ Mock in
strict priority order and picks the deterministic ``MockLLMClient`` when no
key is set and no Ollama server answers (this suite's world, I6); the real
adapters import lazily and are never required; the mock is deterministic
(I8) and answers every prompt family (generation / analyst / challenger)
with valid JSON of the expected shape; there is exactly one canonical port
(the M5 generator re-exports it, no forks).
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest

from quantos.config import Settings
from quantos.llm.client import (
    ClaudeClient,
    LLMClient,
    LLMClientError,
    MockLLMClient,
    OllamaClient,
    OpenRouterClient,
    TracingLLMClient,
    get_llm_client,
    ollama_reachable,
)

NO_OLLAMA = {"probe": lambda url: False}


# ---------------------------------------------------------------------------
# The port is canonical and every backend satisfies it
# ---------------------------------------------------------------------------


class TestPort:
    def test_every_backend_satisfies_the_protocol(self) -> None:
        assert isinstance(MockLLMClient(), LLMClient)
        assert isinstance(ClaudeClient(), LLMClient)
        assert isinstance(OpenRouterClient(api_key="k"), LLMClient)
        assert isinstance(OllamaClient(), LLMClient)
        assert isinstance(TracingLLMClient(MockLLMClient()), LLMClient)

    def test_m5_generator_reexports_the_same_objects(self) -> None:
        """One port, one mock — no duplicate definitions (I7)."""
        from quantos.strategy import generator

        assert generator.LLMClient is LLMClient
        assert generator.MockLLMClient is MockLLMClient


# ---------------------------------------------------------------------------
# Factory resolution: Claude ▸ OpenRouter ▸ Ollama ▸ Mock
# ---------------------------------------------------------------------------


class TestFactory:
    def test_offline_default_is_the_mock(self) -> None:
        """No keys + no Ollama server -> deterministic mock (I6)."""
        client = get_llm_client(env={}, **NO_OLLAMA)
        assert isinstance(client, MockLLMClient)
        assert client.seed == Settings().seed

    def test_claude_wins_when_anthropic_key_is_set(self) -> None:
        env = {"ANTHROPIC_API_KEY": "sk-test", "OPENROUTER_API_KEY": "or-test"}
        client = get_llm_client(env=env, probe=lambda url: True)
        assert isinstance(client, ClaudeClient)
        assert client.api_key == "sk-test"

    def test_openrouter_is_second(self) -> None:
        client = get_llm_client(env={"OPENROUTER_API_KEY": "or-test"}, probe=lambda url: True)
        assert isinstance(client, OpenRouterClient)
        assert client.api_key == "or-test"

    def test_ollama_is_the_free_keyless_third(self) -> None:
        probed: list[str] = []

        def probe(url: str) -> bool:
            probed.append(url)
            return True

        client = get_llm_client(env={"QUANTOS_OLLAMA_URL": "http://box:9999"}, probe=probe)
        assert isinstance(client, OllamaClient)
        assert client.url == "http://box:9999"
        assert probed == ["http://box:9999"]

    def test_env_can_force_a_backend(self) -> None:
        """QUANTOS_LLM_BACKEND=mock beats an available key (explicit wins)."""
        env = {"QUANTOS_LLM_BACKEND": "mock", "ANTHROPIC_API_KEY": "sk-test"}
        assert isinstance(get_llm_client(env=env, **NO_OLLAMA), MockLLMClient)
        env = {"QUANTOS_LLM_BACKEND": "ollama"}
        assert isinstance(get_llm_client(env=env, **NO_OLLAMA), OllamaClient)

    def test_unknown_backend_rejected(self) -> None:
        with pytest.raises(ValueError, match="llm_backend"):
            get_llm_client(env={"QUANTOS_LLM_BACKEND": "skynet"}, **NO_OLLAMA)

    def test_settings_fields_come_from_env(self) -> None:
        settings = Settings.from_env(
            {"QUANTOS_LLM_BACKEND": "ollama", "QUANTOS_OLLAMA_URL": "http://x:1234"}
        )
        assert settings.llm_backend == "ollama"
        assert settings.ollama_url == "http://x:1234"

    def test_no_secret_ever_enters_settings(self) -> None:
        """Keys stay out of the (manifest-pinned) Settings record (I6/I8)."""
        record = json.dumps(Settings.from_env({"ANTHROPIC_API_KEY": "sk-secret"}).as_dict())
        assert "sk-secret" not in record

    def test_langfuse_keys_wrap_with_tracing(self) -> None:
        env = {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}
        client = get_llm_client(env=env, **NO_OLLAMA)
        assert isinstance(client, TracingLLMClient)
        assert isinstance(client.inner, MockLLMClient)


# ---------------------------------------------------------------------------
# Lazy adapters — importable, constructible and failing honestly offline
# ---------------------------------------------------------------------------


class TestLazyAdapters:
    def test_real_sdks_are_not_imported_at_module_import(self) -> None:
        """Importing quantos.llm must not pull anthropic/openai/langfuse (I6)."""
        for name in ("anthropic", "openai", "ollama", "langfuse", "langgraph"):
            assert name not in sys.modules

    def test_claude_complete_raises_llmclienterror_without_sdk(self) -> None:
        assert "anthropic" not in sys.modules  # not installed in this suite
        with pytest.raises(LLMClientError, match="anthropic"):
            ClaudeClient(api_key="sk-test").complete("hello")

    def test_ollama_probe_false_for_dead_port(self) -> None:
        # port 1 on localhost: refused immediately, no network egress
        assert ollama_reachable("http://127.0.0.1:1", timeout=0.05) is False


# ---------------------------------------------------------------------------
# MockLLMClient — deterministic, every prompt family answered validly
# ---------------------------------------------------------------------------


ANALYST_PROMPT = "You are the technical analyst on an investment committee. Return an opinion."
CHALLENGER_PROMPT = (
    "You are the committee's devil's advocate. provisional decision: LONG. Contest it."
)


class TestMockLLMClient:
    def test_deterministic_per_seed_and_prompt(self) -> None:
        for prompt in ("Propose n=4 specs", ANALYST_PROMPT, CHALLENGER_PROMPT, "anything else"):
            a = MockLLMClient(seed=5).complete(prompt)
            b = MockLLMClient(seed=5).complete(prompt)
            assert a == b, prompt
            json.loads(a)  # always valid JSON
        assert MockLLMClient(seed=1).complete(ANALYST_PROMPT) != MockLLMClient(seed=2).complete(
            ANALYST_PROMPT
        )

    def test_generation_prompt_yields_spec_array(self) -> None:
        client = MockLLMClient(seed=3)
        payload = json.loads(client.complete("Propose n=6 distinct strategy specs"))
        assert isinstance(payload, list) and len(payload) == 6
        assert all("rationale" in spec and "indicators" in spec for spec in payload)
        assert client.calls  # the mock records its prompts

    def test_analyst_prompt_yields_valid_opinion(self) -> None:
        opinion: dict[str, Any] = json.loads(MockLLMClient(seed=7).complete(ANALYST_PROMPT))
        assert opinion["direction"] in {"LONG", "SHORT", "FLAT"}
        assert 0.0 <= opinion["confidence"] <= 1.0
        assert opinion["evidence"] and all(
            -1.0 <= item["impact"] <= 1.0 for item in opinion["evidence"]
        )

    def test_challenger_prompt_contests_a_directional_call(self) -> None:
        challenge = json.loads(MockLLMClient(seed=7).complete(CHALLENGER_PROMPT))
        assert challenge["agrees"] is False and challenge["material"] is True
        assert all(item["impact"] < 0 for item in challenge["counter_evidence"])  # against LONG
        flat = json.loads(
            MockLLMClient(seed=7).complete(
                "You are the committee's devil's advocate. provisional decision: FLAT."
            )
        )
        assert flat["agrees"] is True and flat["material"] is False


# ---------------------------------------------------------------------------
# Tracing wrapper — optional, pass-through, never breaking
# ---------------------------------------------------------------------------


class TestTracing:
    def test_injected_tracer_sees_the_call(self) -> None:
        seen: list[tuple[str, str]] = []
        client = TracingLLMClient(MockLLMClient(seed=1), tracer=lambda p, c: seen.append((p, c)))
        result = client.complete("anything else")
        assert seen == [("anything else", result)]

    def test_degrades_to_passthrough_without_langfuse(self) -> None:
        inner = MockLLMClient(seed=1)
        assert TracingLLMClient(inner).complete("anything else") == inner.complete("anything else")

    def test_a_failing_tracer_never_breaks_the_call(self) -> None:
        def boom(prompt: str, completion: str) -> None:
            raise RuntimeError("tracing exploded")

        client = TracingLLMClient(MockLLMClient(seed=1), tracer=boom)
        json.loads(client.complete("anything else"))
