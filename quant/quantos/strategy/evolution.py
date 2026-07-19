"""Genetic evolution of strategy parameters (module 6, WP-5.4).

A dependency-free baseline GA over numpy only (invariant I6): a
:class:`Genome` encodes a spec's tunable numbers (indicator params + rule
thresholds) inside the legal bounds declared by the building-block registry,
and an :class:`Evolver` runs elitist tournament selection, blend crossover
and Gaussian mutation over any fitness function. Everything is a pure
function of ``(template, fitness, seed)`` — same seed, same run (I8).

DEAP / Optuna remain optional accelerators behind the ``[research]`` extra;
nothing here imports them and no test requires them. Fitness functions that
backtest must themselves be deterministic and causal — the natural choice is
the Strategy Lab's DSR-deflated fitness (WP-5.3), which keeps the GA from
evolving toward data-mined luck (I9).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from quantos.strategy.base import Rule, StrategyRegistry, StrategySpec, registry

__all__ = ["EvolutionResult", "Evolver", "Gene", "GenerationStats", "Genome"]


@dataclass(frozen=True)
class Gene:
    """One evolvable number: its name and legal range.

    Attributes:
        name: what the value means (``"zscore.period"``, ``"rule.0.threshold"``).
        low: lower bound (inclusive).
        high: upper bound (inclusive).
        integer: round to an integer when decoding.
    """

    name: str
    low: float
    high: float
    integer: bool = False

    def __post_init__(self) -> None:
        if not self.low <= self.high:
            raise ValueError(f"{self.name}: low {self.low} > high {self.high}")

    def clip(self, value: float) -> float:
        """Clamp a raw value into the legal range (rounding integer genes)."""
        clipped = float(min(max(value, self.low), self.high))
        return float(round(clipped)) if self.integer else clipped

    def sample(self, rng: np.random.Generator) -> float:
        """Draw a uniform value from the legal range."""
        if self.integer:
            return float(rng.integers(int(self.low), int(self.high) + 1))
        return float(rng.uniform(self.low, self.high))

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {"name": self.name, "low": self.low, "high": self.high, "integer": self.integer}


@dataclass(frozen=True)
class Genome:
    """A point in the search space: genes plus their current values.

    Built either directly (pure optimisation problems) or from a
    :class:`StrategySpec` via :meth:`from_spec`, in which case
    :meth:`to_spec` decodes it back into a runnable, hashable spec (I8).
    """

    genes: tuple[Gene, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "genes", tuple(self.genes))
        if len(self.genes) != len(self.values):
            raise ValueError(f"{len(self.values)} values for {len(self.genes)} genes")
        object.__setattr__(
            self,
            "values",
            tuple(g.clip(float(v)) for g, v in zip(self.genes, self.values, strict=True)),
        )
        if not self.genes:
            raise ValueError("Genome needs at least one gene")

    def replace_values(self, values: Sequence[float]) -> Genome:
        """A sibling genome with new (auto-clipped) values."""
        return Genome(self.genes, tuple(float(v) for v in values))

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "genes": [g.as_dict() for g in self.genes],
            "values": {g.name: v for g, v in zip(self.genes, self.values, strict=True)},
        }

    # -- the spec bridge ---------------------------------------------------

    @classmethod
    def from_spec(cls, spec: StrategySpec, blocks: StrategyRegistry | None = None) -> Genome:
        """Encode a spec's indicator params and rule thresholds as a genome.

        Bounds come from the registry's :class:`ParamSpec` declarations, so
        every decoded spec stays inside the grammar the generator (WP-5.2)
        and the lab (WP-5.3) accept.
        """
        reg = blocks if blocks is not None else registry
        genes: list[Gene] = []
        values: list[float] = []
        for name in spec.indicators:
            block = reg.indicator(name)
            for pspec in block.params:
                key = f"{name}.{pspec.name}"
                genes.append(Gene(key, pspec.low, pspec.high, pspec.integer))
                values.append(float(spec.params.get(key, pspec.default)))
        for i, rule in enumerate(spec.rules):
            tspec = reg.indicator(rule.indicator).threshold
            genes.append(Gene(f"rule.{i}.threshold", tspec.low, tspec.high, tspec.integer))
            values.append(float(rule.threshold))
        return cls(tuple(genes), tuple(values))

    def to_spec(self, spec: StrategySpec) -> StrategySpec:
        """Decode the genome back onto ``spec`` (params + rule thresholds)."""
        lookup = {g.name: v for g, v in zip(self.genes, self.values, strict=True)}
        params = {
            key: value for key, value in lookup.items() if not key.startswith("rule.")
        }
        rules = tuple(
            Rule(
                indicator=rule.indicator,
                comparator=rule.comparator,
                threshold=lookup.get(f"rule.{i}.threshold", rule.threshold),
                action=rule.action,
                weight=rule.weight,
            )
            for i, rule in enumerate(spec.rules)
        )
        return spec.with_params(params, rules=rules)


FitnessFn = Callable[[Genome], float]


@dataclass
class GenerationStats:
    """Population fitness statistics for one generation."""

    generation: int
    best: float
    mean: float
    worst: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "generation": self.generation,
            "best": self.best,
            "mean": self.mean,
            "worst": self.worst,
        }


@dataclass
class EvolutionResult:
    """The outcome of an evolution run (fully reproducible, I8)."""

    best: Genome
    best_fitness: float
    history: list[GenerationStats] = field(default_factory=list)
    population: list[Genome] = field(default_factory=list)
    n_evaluations: int = 0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "best": self.best.as_dict(),
            "best_fitness": self.best_fitness,
            "history": [h.as_dict() for h in self.history],
            "n_evaluations": self.n_evaluations,
        }


class Evolver:
    """Elitist tournament GA: selection / crossover / mutation (offline, I6).

    Maximises ``fitness(genome)``. Elites are copied unchanged into the next
    generation (the best never regresses); parents are picked by tournament;
    children are blend-crossovers with per-gene Gaussian mutation, always
    clipped back into the genes' legal bounds.
    """

    def __init__(
        self,
        fitness: FitnessFn,
        population_size: int = 32,
        elite: int = 2,
        tournament_size: int = 3,
        crossover_rate: float = 0.9,
        mutation_rate: float = 0.25,
        mutation_scale: float = 0.15,
        seed: int = 0,
    ) -> None:
        """
        Args:
            fitness: deterministic objective to maximise (I8).
            population_size: genomes per generation.
            elite: top genomes copied unchanged each generation.
            tournament_size: contestants per parent selection.
            crossover_rate: probability a child is a blend of both parents.
            mutation_rate: per-gene probability of Gaussian mutation.
            mutation_scale: mutation std as a fraction of each gene's range.
            seed: RNG seed — the whole run replays from it (I8).
        """
        if population_size < 2:
            raise ValueError(f"population_size must be >= 2, got {population_size}")
        if not 0 <= elite < population_size:
            raise ValueError(f"need 0 <= elite < population_size, got {elite}")
        if tournament_size < 1:
            raise ValueError(f"tournament_size must be >= 1, got {tournament_size}")
        self.fitness = fitness
        self.population_size = population_size
        self.elite = elite
        self.tournament_size = tournament_size
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.mutation_scale = mutation_scale
        self.seed = seed

    # -- operators ---------------------------------------------------------

    def _select(
        self, rng: np.random.Generator, scored: list[tuple[float, Genome]]
    ) -> Genome:
        """Tournament selection: best of ``tournament_size`` random picks."""
        picks = rng.integers(len(scored), size=self.tournament_size)
        best = max(picks, key=lambda i: scored[int(i)][0])
        return scored[int(best)][1]

    def _crossover(self, rng: np.random.Generator, a: Genome, b: Genome) -> Genome:
        """Per-gene blend crossover (falls back to parent ``a``'s values)."""
        if rng.random() >= self.crossover_rate:
            return a
        mix = rng.random(len(a.values))
        child = [
            mix[i] * va + (1.0 - mix[i]) * vb
            for i, (va, vb) in enumerate(zip(a.values, b.values, strict=True))
        ]
        return a.replace_values(child)

    def _mutate(self, rng: np.random.Generator, genome: Genome) -> Genome:
        """Gaussian per-gene mutation, scaled to each gene's range."""
        values = list(genome.values)
        for i, gene in enumerate(genome.genes):
            if rng.random() < self.mutation_rate:
                span = gene.high - gene.low
                values[i] = values[i] + rng.normal(0.0, self.mutation_scale * max(span, 1e-12))
        return genome.replace_values(values)  # replace_values clips into bounds

    # -- the run -----------------------------------------------------------

    def evolve(self, template: Genome, generations: int = 15) -> EvolutionResult:
        """Run the GA from a template genome.

        Args:
            template: defines the gene space; its values seed one individual,
                the rest of generation 0 is sampled uniformly in-bounds.
            generations: generations to evolve (>= 1).

        Returns:
            An :class:`EvolutionResult` whose ``history`` records best/mean/
            worst fitness per generation — with elitism the best is
            monotonically non-decreasing, and on a well-posed fitness the
            population mean improves across generations (the WP-5.4
            acceptance criterion).
        """
        if generations < 1:
            raise ValueError(f"generations must be >= 1, got {generations}")
        rng = np.random.default_rng(self.seed)
        cache: dict[tuple[float, ...], float] = {}
        evaluations = 0

        def score(genome: Genome) -> float:
            nonlocal evaluations
            if genome.values not in cache:
                cache[genome.values] = float(self.fitness(genome))
                evaluations += 1
            return cache[genome.values]

        population = [template] + [
            template.replace_values([g.sample(rng) for g in template.genes])
            for _ in range(self.population_size - 1)
        ]

        history: list[GenerationStats] = []
        scored: list[tuple[float, Genome]] = []
        for generation in range(generations):
            scored = sorted(
                ((score(g), g) for g in population), key=lambda t: t[0], reverse=True
            )
            fits = [f for f, _ in scored]
            history.append(
                GenerationStats(
                    generation=generation,
                    best=fits[0],
                    mean=float(np.mean(fits)),
                    worst=fits[-1],
                )
            )
            if generation == generations - 1:
                break
            next_population = [g for _, g in scored[: self.elite]]
            while len(next_population) < self.population_size:
                parent_a = self._select(rng, scored)
                parent_b = self._select(rng, scored)
                child = self._mutate(rng, self._crossover(rng, parent_a, parent_b))
                next_population.append(child)
            population = next_population

        best_fitness, best = scored[0]
        return EvolutionResult(
            best=best,
            best_fitness=best_fitness,
            history=history,
            population=[g for _, g in scored],
            n_evaluations=evaluations,
        )

    def evolve_spec(
        self,
        spec: StrategySpec,
        generations: int = 15,
        blocks: StrategyRegistry | None = None,
    ) -> tuple[StrategySpec, EvolutionResult]:
        """Evolve a spec's parameters in place of a raw genome (convenience).

        The fitness function still receives :class:`Genome` instances; use
        ``genome.to_spec(spec)`` inside it to backtest the decoded candidate
        (e.g. through the Strategy Lab's DSR-deflated fitness, I9).

        Returns:
            ``(best_spec, result)`` where ``best_spec`` is the decoded
            winner — a valid, hashable spec inside the registry's bounds.
        """
        result = self.evolve(Genome.from_spec(spec, blocks=blocks), generations=generations)
        return result.best.to_spec(spec), result
