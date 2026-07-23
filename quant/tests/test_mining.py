"""Auto-mining: keep digging, save the gold to a ranked, deduped vault (I8/I9)."""

from __future__ import annotations

from pathlib import Path

from quantos.mining import GoldStrategy, StrategyMiner, StrategyVault


def gold(hash_: str, dsr: float, oos: float = 1.0) -> GoldStrategy:
    return GoldStrategy(
        spec={"name": hash_},
        spec_hash=hash_,
        family="trend",
        name=hash_,
        oos_sharpe=oos,
        deflated_sharpe=dsr,
        regime="TREND_UP",
        found_round=0,
    )


class TestVault:
    def test_add_dedupes_and_ranks(self, tmp_path: Path) -> None:
        vault = StrategyVault(path=tmp_path / "v.json", max_size=10)
        assert vault.add([gold("a", 0.7), gold("b", 0.9)]) == 2
        assert vault.add([gold("a", 0.7)]) == 0  # already there — not new (I8)
        assert [g.spec_hash for g in vault.top()] == ["b", "a"]  # best (higher DSR) first

    def test_keeps_only_the_best_when_full(self, tmp_path: Path) -> None:
        vault = StrategyVault(path=tmp_path / "v.json", max_size=2)
        vault.add([gold("a", 0.5), gold("b", 0.9), gold("c", 0.7)])
        assert [g.spec_hash for g in vault.top()] == ["b", "c"]  # weakest ("a") dropped
        assert len(vault) == 2

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "v.json"
        StrategyVault(path=path).add([gold("a", 0.8)])
        assert len(StrategyVault(path=path)) == 1  # survives a restart

    def test_clear(self, tmp_path: Path) -> None:
        vault = StrategyVault(path=tmp_path / "v.json")
        vault.add([gold("a", 0.8)])
        vault.clear()
        assert len(vault) == 0


class TestMiner:
    def test_dig_saves_gold(self, tmp_path: Path) -> None:
        vault = StrategyVault(path=tmp_path / "v.json")
        miner = StrategyMiner(vault=vault, force_synthetic=True, n_candidates=30, min_dsr=0.6)
        summary = miner.dig(round_index=0)
        assert summary["tested"] == 30
        assert summary["gold_found"] >= 1  # found some validated strategies
        assert len(vault) == summary["vault_size"]

    def test_candidates_count_is_configurable(self, tmp_path: Path) -> None:
        """More candidates per round = more tested; the DSR gate auto-adjusts."""
        vault = StrategyVault(path=tmp_path / "v.json")
        summary = StrategyMiner(vault=vault, force_synthetic=True, n_candidates=50).dig(0)
        assert summary["tested"] == 50  # honours the requested batch size

    def test_run_loops_and_accumulates(self, tmp_path: Path) -> None:
        vault = StrategyVault(path=tmp_path / "v.json")
        miner = StrategyMiner(vault=vault, force_synthetic=True, n_candidates=30)
        seen: list[dict] = []
        # sleep is injected as a no-op — the loop never actually waits.
        done = miner.run(rounds=3, on_round=seen.append, sleep=lambda _s: None)
        assert done == 3
        assert len(seen) == 3
        assert len(vault) > 0  # gold accumulated while "away"

    def test_a_failing_round_never_stops_mining(self, tmp_path: Path) -> None:
        vault = StrategyVault(path=tmp_path / "v.json")
        miner = StrategyMiner(vault=vault, force_synthetic=True)

        def boom(_round: int) -> dict:
            raise RuntimeError("data hiccup")

        miner.dig = boom  # type: ignore[method-assign]
        summaries: list[dict] = []
        done = miner.run(rounds=2, on_round=summaries.append, sleep=lambda _s: None)
        assert done == 0  # both rounds failed
        assert all("error" in s for s in summaries)  # but the loop kept going (I6)
