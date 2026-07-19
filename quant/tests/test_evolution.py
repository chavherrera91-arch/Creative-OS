"""WP-5.4 — Genetic evolution: Genome encoding + dependency-free Evolver.

Acceptance: on a fitness with a known optimum the mean population fitness
improves across generations, deterministically for a fixed seed (I8); the
genome round-trips a spec's params and rule thresholds inside the registry
bounds, so every evolved candidate is a valid, runnable spec.
"""

from __future__ import annotations

import pytest

from quantos.strategy.base import Rule, StrategySpec
from quantos.strategy.evolution import Evolver, Gene, Genome
from quantos.strategy.generator import validate_spec

OPTIMUM = (7.3, 2.4, 5.0)


def _quadratic(genome: Genome) -> float:
    """Known optimum at ``OPTIMUM`` (fitness 0.0, negative elsewhere)."""
    return -sum((v - o) ** 2 for v, o in zip(genome.values, OPTIMUM, strict=True))


def _template() -> Genome:
    genes = (
        Gene("x", 0.0, 10.0),
        Gene("y", 0.0, 10.0),
        Gene("k", 0.0, 10.0, integer=True),
    )
    return Genome(genes, (0.0, 10.0, 0.0))


# ---------------------------------------------------------------------------
# The GA on a known optimum
# ---------------------------------------------------------------------------


def test_mean_population_fitness_improves_across_generations() -> None:
    result = Evolver(_quadratic, population_size=24, seed=42).evolve(_template(), generations=20)
    assert len(result.history) == 20
    first, last = result.history[0], result.history[-1]
    # the acceptance criterion: the population as a whole gets better
    assert last.mean > first.mean
    # elitism: the best individual never regresses
    bests = [h.best for h in result.history]
    assert all(b2 >= b1 for b1, b2 in zip(bests[:-1], bests[1:], strict=True))
    # and the winner is close to the known optimum
    assert result.best_fitness > -0.5
    assert abs(result.best.values[0] - OPTIMUM[0]) < 1.0
    assert abs(result.best.values[1] - OPTIMUM[1]) < 1.0
    assert result.best.values[2] == 5.0  # integer gene decodes to an integer


def test_evolution_is_deterministic_for_a_fixed_seed(assert_reproducible) -> None:
    def run() -> dict:
        return Evolver(_quadratic, population_size=16, seed=7).evolve(
            _template(), generations=8
        ).as_dict()

    assert_reproducible(run)
    other = Evolver(_quadratic, population_size=16, seed=8).evolve(_template(), generations=8)
    assert other.as_dict() != run()  # a different seed explores differently


def test_mutation_and_crossover_respect_gene_bounds() -> None:
    result = Evolver(
        _quadratic, population_size=20, mutation_rate=1.0, mutation_scale=2.0, seed=3
    ).evolve(_template(), generations=6)
    for genome in result.population:
        for gene, value in zip(genome.genes, genome.values, strict=True):
            assert gene.low <= value <= gene.high
            if gene.integer:
                assert value == round(value)


def test_evolver_validates_configuration() -> None:
    with pytest.raises(ValueError):
        Evolver(_quadratic, population_size=1)
    with pytest.raises(ValueError):
        Evolver(_quadratic, elite=32, population_size=8)
    with pytest.raises(ValueError):
        Evolver(_quadratic, tournament_size=0)
    with pytest.raises(ValueError):
        Evolver(_quadratic).evolve(_template(), generations=0)
    with pytest.raises(ValueError):
        Genome((Gene("x", 0.0, 1.0),), (0.5, 0.7))  # values/genes mismatch
    with pytest.raises(ValueError):
        Gene("bad", 2.0, 1.0)


# ---------------------------------------------------------------------------
# The spec bridge: genomes encode/decode real strategies
# ---------------------------------------------------------------------------


SPEC = StrategySpec(
    name="evolvable",
    family="mean_reversion",
    indicators=("zscore",),
    rules=(Rule("zscore", "gt", 1.0, -1), Rule("zscore", "lt", -1.0, 1)),
    params={"zscore.period": 20.0},
    target_regimes=("RANGE",),
)


def test_genome_roundtrips_a_spec() -> None:
    genome = Genome.from_spec(SPEC)
    assert {g.name for g in genome.genes} == {
        "zscore.period",
        "rule.0.threshold",
        "rule.1.threshold",
    }
    decoded = genome.to_spec(SPEC)
    assert decoded == SPEC  # unchanged values decode to the identical spec
    assert decoded.spec_hash() == SPEC.spec_hash()

    moved = genome.replace_values([35.0, 2.0, -2.0]).to_spec(SPEC)
    assert moved.params["zscore.period"] == 35.0
    assert moved.rules[0].threshold == 2.0 and moved.rules[1].threshold == -2.0
    assert moved.spec_hash() != SPEC.spec_hash()  # a new, version-pinned identity
    assert validate_spec(moved)  # still runnable inside the grammar


def test_evolve_spec_converges_toward_a_target_parameterisation() -> None:
    target = {"zscore.period": 40.0, "rule.0.threshold": 2.0, "rule.1.threshold": -2.0}

    def fitness(genome: Genome) -> float:
        values = {g.name: v for g, v in zip(genome.genes, genome.values, strict=True)}
        return -sum((values[k] - t) ** 2 for k, t in target.items())

    best_spec, result = Evolver(fitness, population_size=24, seed=5).evolve_spec(
        SPEC, generations=15
    )
    assert result.history[-1].mean > result.history[0].mean
    assert abs(best_spec.params["zscore.period"] - 40.0) <= 3.0
    assert abs(best_spec.rules[0].threshold - 2.0) < 0.5
    # every evolved candidate stayed inside the registry's legal bounds
    assert validate_spec(best_spec)
    tspec = SPEC  # decoding preserves structure: same blocks, rules, regimes
    assert best_spec.indicators == tspec.indicators
    assert best_spec.family == tspec.family
    assert best_spec.target_regimes == tspec.target_regimes
