"""WP-5.2 — Strategy generator: deterministic grammar search + optional LLM.

Acceptance: ``generate(100)`` yields 100 unique, valid specs offline and
deterministically for a fixed seed (I6/I8); the diversity metric clears its
gate (no duplicate indicator sets); the LLM path is exercised with
``MockLLMClient`` only and is never required; every returned spec is a
runnable :class:`Strategy`.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import pytest

from quantos.strategy.base import StrategySpec, compile_spec
from quantos.strategy.generator import (
    DEFAULT_FAMILIES,
    FamilyTemplate,
    GenerationError,
    LLMClient,
    LLMStrategyGenerator,
    MockLLMClient,
    RandomStrategyGenerator,
    diversity_score,
    generate,
    validate_spec,
)

# ---------------------------------------------------------------------------
# Default backend: deterministic grammar search
# ---------------------------------------------------------------------------


def test_generate_100_unique_valid_specs_deterministically() -> None:
    specs = generate(100, seed=123)
    assert len(specs) == 100
    # unique on content hash AND on indicator set (no duplicate sets)
    assert len({s.spec_hash() for s in specs}) == 100
    assert len({s.indicator_set() for s in specs}) == 100
    # diversity metric above the default gate
    assert diversity_score(specs) >= 0.25
    # every spec is valid, versioned, family-tagged and regime-targeted
    known_families = {f.name for f in DEFAULT_FAMILIES}
    for spec in specs:
        assert spec.version
        assert spec.family in known_families
        assert spec.target_regimes
        assert spec.rationale
        assert validate_spec(spec)
    # deterministic for a fixed seed (I8)
    replay = generate(100, seed=123)
    assert [s.as_dict() for s in replay] == [s.as_dict() for s in specs]


def test_different_seed_different_batch() -> None:
    a = generate(15, seed=1)
    b = generate(15, seed=2)
    assert [s.as_dict() for s in a] != [s.as_dict() for s in b]


def test_generated_specs_compile_and_run(ohlcv: pd.DataFrame) -> None:
    for spec in generate(5, seed=9):
        signals = compile_spec(spec).signals(ohlcv)
        assert signals.index.equals(ohlcv.index)
        assert signals.between(-1.0, 1.0).all()


def test_unreachable_batch_size_raises() -> None:
    tiny = RandomStrategyGenerator(
        families=(
            FamilyTemplate(
                "trend", ("ema_ratio", "sma_ratio", "momentum"), ("gt", "lt"), ("TREND_UP",), "x"
            ),
        )
    )
    # only 7 distinct indicator sets exist over a 3-block pool
    with pytest.raises(GenerationError, match="valid unique specs"):
        tiny.generate(10, seed=0)


def test_diversity_gate_enforced() -> None:
    with pytest.raises(GenerationError, match="diversity"):
        generate(60, seed=0, diversity=0.99)


def test_generator_rejects_bad_n() -> None:
    with pytest.raises(ValueError):
        generate(0)
    with pytest.raises(ValueError):
        LLMStrategyGenerator(MockLLMClient()).generate(0)


def test_diversity_score_metric() -> None:
    a = StrategySpec.from_dict(generate(1, seed=3)[0].as_dict())
    assert diversity_score([a]) == 1.0
    assert diversity_score([a, a.with_params({})]) == 0.0  # identical indicator sets
    specs = generate(10, seed=3)
    assert 0.0 < diversity_score(specs) <= 1.0


# ---------------------------------------------------------------------------
# Optional LLM backend (mock only — never a real model, I6)
# ---------------------------------------------------------------------------


def test_mock_llm_client_is_deterministic_and_satisfies_the_port() -> None:
    assert isinstance(MockLLMClient(), LLMClient)
    a = MockLLMClient(seed=5).complete("Propose n=6 specs")
    b = MockLLMClient(seed=5).complete("Propose n=6 specs")
    assert a == b
    assert len(json.loads(a)) == 6


def test_llm_generator_yields_validated_specs() -> None:
    client = MockLLMClient(seed=7)
    specs = LLMStrategyGenerator(client).generate(8, diversity=0.2)
    assert len(specs) == 8
    assert len({s.spec_hash() for s in specs}) == 8
    assert len({s.indicator_set() for s in specs}) == 8
    assert all(validate_spec(s) for s in specs)
    assert all("mock LLM" in s.rationale for s in specs)
    # the prompt stated the grammar and the research-only stance
    assert client.calls and "ema_ratio" in client.calls[0] and "no live trading" in client.calls[0]
    # deterministic: a fresh identically-seeded client replays the batch (I8)
    replay = LLMStrategyGenerator(MockLLMClient(seed=7)).generate(8, diversity=0.2)
    assert [s.as_dict() for s in replay] == [s.as_dict() for s in specs]


class _BrokenJSONClient:
    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        return "this is not json"


class _PartiallyValidClient:
    """Returns one malformed proposal plus enough valid ones."""

    def complete(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        good = [s.as_dict() for s in RandomStrategyGenerator().generate(5, seed=11)]
        return json.dumps([{"name": "broken-no-indicators"}, *good])


def test_llm_generator_rejects_malformed_json() -> None:
    with pytest.raises(GenerationError, match="malformed JSON"):
        LLMStrategyGenerator(_BrokenJSONClient()).generate(3)


def test_llm_generator_skips_invalid_proposals() -> None:
    specs = LLMStrategyGenerator(_PartiallyValidClient()).generate(5, diversity=0.2)
    assert len(specs) == 5
    assert all(validate_spec(s) for s in specs)
    # but an under-filled batch is an honest failure, not silent padding
    with pytest.raises(GenerationError, match="valid unique specs"):
        LLMStrategyGenerator(_PartiallyValidClient()).generate(9)
