"""CLI research commands — full analyst panel by default + honesty layer (I9)."""

from __future__ import annotations

import pytest

from quantos.cli import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    code = main(list(argv))
    assert code == 0
    return capsys.readouterr().out


class TestDecidePanel:
    def test_full_panel_votes_by_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = run(
            capsys, "decide", "--symbol", "BTC/USDT", "--bars", "300", "--seed", "7", "--synthetic"
        )
        # All five analysts participate — no channel is missing by default.
        assert "no macro channel" not in out
        assert "no sentiment channel" not in out
        assert "no on-chain channel" not in out

    def test_no_channels_makes_them_abstain(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = run(
            capsys,
            "decide",
            "--symbol",
            "BTC/USDT",
            "--bars",
            "300",
            "--seed",
            "7",
            "--synthetic",
            "--no-channels",
        )
        assert "no macro channel" in out  # opt-out restores price-only


class TestBacktestHonesty:
    def test_backtest_reports_deflated_sharpe(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = run(
            capsys,
            "backtest",
            "--symbol",
            "BTC/USDT",
            "--bars",
            "300",
            "--seed",
            "7",
            "--synthetic",
        )
        # The statistical-honesty layer is always surfaced (I9).
        assert "reality check" in out
        assert "deflated_sharpe_prob_edge_positive" in out
