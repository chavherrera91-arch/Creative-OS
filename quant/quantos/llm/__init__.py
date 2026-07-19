"""LLM access layer (M6): one canonical port, four backends, zero required deps.

``quantos.llm.client`` defines the :class:`~quantos.llm.client.LLMClient`
Protocol every AI-facing module speaks (strategy generation, LLM analysts,
the AI Challenger) and :func:`~quantos.llm.client.get_llm_client`, the factory
that resolves the best available backend — Claude ▸ OpenRouter ▸ Ollama ▸
deterministic Mock — without ever requiring a key or the network (I6).
"""

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
