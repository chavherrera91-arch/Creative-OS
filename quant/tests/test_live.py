"""Live paper trading — accumulates a fake-money account, never real capital (I1)."""

from __future__ import annotations

from pathlib import Path

from quantos.live import LivePaperTrader


def trader(tmp_path: Path) -> LivePaperTrader:
    # force_synthetic keeps the test fully offline and deterministic (I6/I8).
    return LivePaperTrader(
        symbol="BTC/USDT",
        state_path=tmp_path / "demo.json",
        force_synthetic=True,
    )


class TestLivePaper:
    def test_step_is_paper_and_accumulates(self, tmp_path: Path) -> None:
        t = trader(tmp_path)
        for _ in range(3):
            step = t.step()
            assert step["is_paper"] is True  # never real capital (I1)
            assert step["equity"] > 0
        account = t.account()
        assert len(account["history"]) == 3  # the demo account grows across steps
        assert (tmp_path / "demo.json").exists()  # persisted to disk

    def test_reset_wipes_the_account(self, tmp_path: Path) -> None:
        t = trader(tmp_path)
        t.step()
        assert t.account()["history"]
        t.reset()
        assert t.account()["history"] == []  # back to a fresh demo account

    def test_offline_source_is_labelled_honestly(self, tmp_path: Path) -> None:
        step = trader(tmp_path).step()
        assert step["source"] == "synthetic"  # never claims 'real' when offline (I3)

    def test_no_live_execution_path(self, tmp_path: Path) -> None:
        t = trader(tmp_path)
        for attribute in ("submit_live", "go_live", "execute_real"):
            assert not hasattr(t, attribute)
