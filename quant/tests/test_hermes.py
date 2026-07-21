"""WP-8.3 — Hermes: alerts out, answers from the record, strictly read-only (I1)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantos.committee.committee import default_committee
from quantos.data.models import MarketSnapshot
from quantos.hermes import (
    ConsoleChannel,
    DiscordChannel,
    EmailChannel,
    Hermes,
    HermesEvent,
    Notifier,
    TelegramChannel,
    event_from_decision,
    format_alert,
)
from quantos.memory import DecisionArchive


def snapshot(ohlcv: pd.DataFrame) -> MarketSnapshot:
    return MarketSnapshot(
        "BTC/USDT",
        "1h",
        ohlcv,
        macro={"dxy_trend": -0.9, "risk_appetite": 0.9},
        sentiment={"score": 0.6},
        onchain={"whale_accumulation": 0.8},
    )


def archived_record(
    symbol: str = "BTC/USDT", as_of: str = "2024-02-01T00:00:00+00:00", regime: str = "TREND_UP"
) -> dict:
    return {
        "symbol": symbol,
        "timeframe": "1h",
        "price": 100.0,
        "direction": "LONG",
        "approved": True,
        "confidence": 0.9,
        "blocked_by_risk": False,
        "reasons": ["breakout confirmed by volume"],
        "opinions": [],
        "regime": {"label": regime},
        "strategies_considered": [{"name": "breakout-1", "family": "breakout"}],
        "run_manifest": {"seed": 42},
        "as_of": as_of,
    }


def messenger(client: object | None = None) -> tuple[Hermes, ConsoleChannel, DecisionArchive]:
    channel = ConsoleChannel(echo=False)
    archive = DecisionArchive()
    agent = Hermes(archive, Notifier([channel]), client=client)  # type: ignore[arg-type]
    return agent, channel, archive


class TestOutbound:
    def test_decision_alert_reaches_the_console(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(snapshot(uptrend_ohlcv))
        agent, channel, _ = messenger()
        agent.announce(decision)
        assert len(channel.sent) == 1
        alert = channel.sent[0]
        assert alert.startswith("[quantos][")  # canonical header
        assert "BTC/USDT" in alert
        assert "INVESTMENT COMMITTEE" in alert  # body is the recorded narrative (I4)

    def test_veto_becomes_a_veto_event(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(snapshot(uptrend_ohlcv))
        event = event_from_decision(decision)
        if decision.blocked_by_risk:
            assert event.kind == "veto"
        else:
            assert event.kind == "decision"
        assert event.dedupe_key  # content-hash identity (I8)

    def test_same_decision_is_delivered_once(self, uptrend_ohlcv: pd.DataFrame) -> None:
        decision = default_committee().deliberate(snapshot(uptrend_ohlcv))
        agent, channel, _ = messenger()
        agent.announce(decision)
        agent.announce(decision)
        assert len(channel.sent) == 1  # deduped by content hash

    def test_rate_limit_uses_the_injected_clock(self) -> None:
        channel = ConsoleChannel(echo=False)
        now = {"t": 0.0}
        notifier = Notifier(
            [channel], max_per_window=2, window_seconds=60.0, clock=lambda: now["t"]
        )
        for i in range(3):
            notifier.notify(HermesEvent(kind="anomaly", title=f"a{i}"))
        assert len(channel.sent) == 2  # third hits the per-kind budget
        now["t"] = 61.0  # window slides
        assert notifier.notify(HermesEvent(kind="anomaly", title="a3"))
        assert len(channel.sent) == 3

    def test_routing_per_kind(self) -> None:
        default, urgent = ConsoleChannel(echo=False), ConsoleChannel(echo=False)
        notifier = Notifier([default], routes={"veto": [urgent]})
        notifier.notify(HermesEvent(kind="decision", title="d"))
        notifier.notify(HermesEvent(kind="veto", title="v"))
        assert len(default.sent) == 1 and len(urgent.sent) == 1
        assert "[VETO]" in urgent.sent[0]

    def test_unknown_event_kind_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            HermesEvent(kind="gossip", title="nope")

    def test_alert_format(self) -> None:
        event = HermesEvent(kind="digest", title="daily digest", body="all quiet")
        assert format_alert(event) == "[quantos][DIGEST] daily digest\nall quiet"


class TestInbound:
    def test_answer_comes_from_the_archived_record(self) -> None:
        agent, _, archive = messenger()
        did = archive.record(archived_record())
        archive.record_outcome(did, pnl=42.0, notes="target hit")
        answer = agent.answer("what happened with BTC breakout?")
        assert did in answer  # cites the episode it is quoting (I4)
        assert "LONG BTC/USDT" in answer
        assert "won" in answer

    def test_honest_when_the_record_is_silent(self) -> None:
        agent, _, _ = messenger()
        answer = agent.answer("anything about dogecoin?")
        assert "nothing" in answer.lower()  # honest abstention, no invention (I3)

    def test_mock_llm_gets_the_templated_summary(self) -> None:
        from quantos.llm.client import MockLLMClient

        agent, _, archive = messenger(client=MockLLMClient(seed=1))
        archive.record(archived_record())
        answer = agent.answer("BTC breakout?")
        assert "From the decision archive" in answer  # template, not mock JSON

    def test_llm_failure_falls_back_to_the_template(self) -> None:
        class Exploding:
            def complete(self, prompt: str, schema: dict | None = None) -> str:
                raise RuntimeError("backend down")

        agent, _, archive = messenger(client=Exploding())
        archive.record(archived_record())
        answer = agent.answer("BTC breakout?")
        assert "From the decision archive" in answer  # phrasing is optional (I6)


class TestChannels:
    def test_real_channels_require_env_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "DISCORD_WEBHOOK_URL",
            "SMTP_HOST",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "EMAIL_TO",
        ):
            monkeypatch.delenv(name, raising=False)
        for channel_cls in (TelegramChannel, DiscordChannel, EmailChannel):
            with pytest.raises(ValueError):  # tokens come only from env, never code
                channel_cls()

    def test_console_channel_captures(self) -> None:
        channel = ConsoleChannel(echo=False)
        channel.send("hello")
        assert channel.sent == ["hello"]


class TestReadOnlyGuard:
    """Hermes can never place an order or touch execution state (I1)."""

    def test_hermes_sources_never_touch_execution(self) -> None:
        package = Path(__file__).resolve().parents[1] / "quantos" / "hermes"
        forbidden = ("quantos.execution", "quantos.paper", "PaperBroker", ".submit(")
        for source in sorted(package.glob("*.py")):
            text = source.read_text()
            for token in forbidden:
                assert token not in text, f"{source.name} references {token!r}"

    def test_agent_exposes_no_execution_path(self) -> None:
        agent, _, _ = messenger()
        for attribute in ("submit", "execute", "place_order", "trade", "set_limit"):
            assert not hasattr(agent, attribute)
