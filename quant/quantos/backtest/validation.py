"""Statistical validation: anti-overfitting statistics (module 25, I9).

The three tools that separate a real edge from data-mined noise:

- :func:`deflated_sharpe` — the Deflated Sharpe Ratio (Bailey & López de
  Prado): the probability that a Sharpe is positive **after** correcting for
  the number of trials that produced it and for non-normal returns. Selecting
  the best of N backtests inflates the expected maximum Sharpe; the DSR
  deflates it back.
- :func:`pbo` — the Probability of Backtest Overfitting via combinatorially
  symmetric cross-validation (CSCV): how often the in-sample winner falls
  below the out-of-sample median.
- :class:`CombinatorialPurgedCV` — combinatorial cross-validation with
  **purging** (train samples whose label window overlaps a test window are
  dropped) and an **embargo** (train samples immediately after a test block
  are dropped), so overlapping-label leakage is impossible.

Everything is numpy-only and deterministic (I8): the normal CDF uses
``math.erf`` and the inverse CDF is implemented in-house (Acklam's rational
approximation). Sharpe inputs are **per-period** (non-annualised) unless
stated otherwise.

Invariant I9 wiring: :func:`quantos.backtest.walk_forward.walk_forward`
attaches a :func:`deflated_sharpe_from_returns` report to every out-of-sample
result, so no edge is ever claimed from a single split without its DSR.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "CombinatorialPurgedCV",
    "deflated_sharpe",
    "deflated_sharpe_from_returns",
    "expected_max_sharpe",
    "norm_cdf",
    "norm_ppf",
    "pbo",
    "probabilistic_sharpe",
]

#: Euler–Mascheroni constant (expected-maximum approximation).
_EULER_GAMMA = 0.5772156649015329


# -- in-house normal distribution (no scipy, I6) ----------------------------


def norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (stdlib ``math.erf``)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation).

    Accurate to ~1.15e-9 over the open interval (0, 1).

    Raises:
        ValueError: when ``p`` is outside (0, 1).
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    a = (
        -3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
        1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
        6.680131188771972e01, -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
        -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
        3.754408661907416e00,
    )
    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
    )


# -- Deflated Sharpe Ratio ---------------------------------------------------


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """Expected maximum Sharpe among ``n_trials`` skill-less trials.

    The threshold a data-mined "best of N" Sharpe must clear before it means
    anything: ``sqrt(V) * ((1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e)))`` where ``V``
    is the cross-trial variance of the Sharpe estimates.

    Args:
        n_trials: number of independent strategy trials examined.
        var_trials: variance of the Sharpe estimates across those trials.

    Returns:
        The expected maximum (0.0 for a single trial: nothing was selected).
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if n_trials == 1 or var_trials <= 0.0:
        return 0.0
    return math.sqrt(var_trials) * (
        (1.0 - _EULER_GAMMA) * norm_ppf(1.0 - 1.0 / n_trials)
        + _EULER_GAMMA * norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    )


def probabilistic_sharpe(
    sharpe: float, benchmark: float, n_obs: int, skew: float = 0.0, kurtosis: float = 3.0
) -> float:
    """Probabilistic Sharpe Ratio: P(true Sharpe > ``benchmark``).

    Adjusts the estimate's standard error for skewed / fat-tailed returns.

    Args:
        sharpe: observed per-period Sharpe ratio.
        benchmark: Sharpe threshold to beat (e.g. the expected max of N trials).
        n_obs: number of return observations behind the estimate.
        skew: sample skewness of the returns.
        kurtosis: sample (Pearson) kurtosis of the returns — 3.0 for normal.

    Returns:
        The probability in [0, 1]; 0.0 when the estimate has no support
        (fewer than 2 observations or a degenerate variance term).
    """
    if n_obs < 2:
        return 0.0
    variance_term = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if variance_term <= 0.0:
        return 0.0
    z = (sharpe - benchmark) * math.sqrt(n_obs - 1) / math.sqrt(variance_term)
    return norm_cdf(z)


def deflated_sharpe(
    sharpe: float,
    n_trials: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    n_obs: int = 0,
    var_trials: float | None = None,
) -> float:
    """Deflated Sharpe Ratio: P(true Sharpe > 0) after multiple testing (I9).

    The observed Sharpe is benchmarked against the **expected maximum** Sharpe
    of ``n_trials`` skill-less trials — the more strategies were tried, the
    higher the bar and the smaller the DSR — with the standard error corrected
    for skew and fat tails.

    Args:
        sharpe: observed per-period Sharpe of the *selected* strategy.
        n_trials: number of strategy trials examined during the selection.
        skew: sample skewness of the strategy's returns.
        kurtosis: sample (Pearson) kurtosis of the returns — 3.0 for normal.
        n_obs: number of return observations behind the estimate.
        var_trials: variance of the Sharpe estimates across trials; when
            omitted it defaults to the estimator variance of the observed
            Sharpe itself, ``(1 - skew·SR + (kurt-1)/4·SR²) / (n_obs - 1)``.

    Returns:
        The DSR in [0, 1] — the probability the selected strategy's true
        Sharpe is positive once the selection process is accounted for.
    """
    if n_obs < 2:
        return 0.0
    if var_trials is None:
        variance_term = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
        var_trials = max(variance_term, 0.0) / (n_obs - 1)
    benchmark = expected_max_sharpe(n_trials, var_trials)
    return probabilistic_sharpe(sharpe, benchmark, n_obs, skew, kurtosis)


def deflated_sharpe_from_returns(
    returns: pd.Series, n_trials: int = 1, var_trials: float | None = None
) -> dict[str, float]:
    """Compute the DSR and its ingredients straight from a return series.

    Args:
        returns: per-bar simple returns (NaNs treated as flat bars).
        n_trials: number of strategy trials behind the selection (I9).
        var_trials: optional cross-trial Sharpe variance (see
            :func:`deflated_sharpe`).

    Returns:
        Dict with ``sharpe`` (per-period), ``skew``, ``kurtosis``, ``n_obs``,
        ``n_trials``, ``expected_max_sharpe`` and ``deflated_sharpe`` — the
        report every OOS evaluation must carry (I9).
    """
    values = returns.fillna(0.0).to_numpy(dtype=float)
    n = len(values)
    if n < 2:
        return {
            "sharpe": 0.0, "skew": 0.0, "kurtosis": 3.0, "n_obs": float(n),
            "n_trials": float(n_trials), "expected_max_sharpe": 0.0, "deflated_sharpe": 0.0,
        }
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    sharpe = mean / std if std > 0.0 else 0.0
    centred = values - mean
    m2 = float((centred**2).mean())
    if m2 > 0.0:
        skew = float((centred**3).mean() / m2**1.5)
        kurt = float((centred**4).mean() / m2**2)
    else:
        skew, kurt = 0.0, 3.0
    if var_trials is None:
        variance_term = 1.0 - skew * sharpe + (kurt - 1.0) / 4.0 * sharpe**2
        var_used = max(variance_term, 0.0) / (n - 1)
    else:
        var_used = var_trials
    return {
        "sharpe": sharpe,
        "skew": skew,
        "kurtosis": kurt,
        "n_obs": float(n),
        "n_trials": float(n_trials),
        "expected_max_sharpe": expected_max_sharpe(n_trials, var_used),
        "deflated_sharpe": deflated_sharpe(
            sharpe, n_trials, skew=skew, kurtosis=kurt, n_obs=n, var_trials=var_used
        ),
    }


# -- Probability of Backtest Overfitting -------------------------------------


def _column_sharpes(matrix: np.ndarray) -> np.ndarray:
    """Per-column per-period Sharpe; degenerate columns rank last."""
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0, ddof=1)
    return np.where(std > 0.0, mean / np.where(std > 0.0, std, 1.0), -np.inf)


def pbo(
    is_returns: pd.DataFrame | np.ndarray,
    oos_returns: pd.DataFrame | np.ndarray,
    n_blocks: int = 8,
) -> float:
    """Probability of Backtest Overfitting via CSCV (I9).

    The IS and OOS return panels (rows = time, columns = strategy trials) are
    stacked and re-split into every combinatorially symmetric half: for each
    of the ``C(n_blocks, n_blocks/2)`` block combinations the in-sample winner
    is selected and its **out-of-sample relative rank** recorded. PBO is the
    fraction of combinations where the IS winner performs at or below the OOS
    median — near 0 for a genuine edge, near 0.5 for pure selection noise.

    Args:
        is_returns: in-sample per-bar returns, one column per trial.
        oos_returns: out-of-sample returns for the same trials (same columns).
        n_blocks: number of time blocks for CSCV (must be even).

    Returns:
        PBO in [0, 1].

    Raises:
        ValueError: on mismatched panels, odd ``n_blocks``, or too few rows.
    """
    is_m = np.asarray(is_returns, dtype=float)
    oos_m = np.asarray(oos_returns, dtype=float)
    if is_m.ndim != 2 or oos_m.ndim != 2:
        raise ValueError("is_returns and oos_returns must be 2-D (time x trials)")
    if is_m.shape[1] != oos_m.shape[1]:
        raise ValueError(
            f"panels disagree on trial count: {is_m.shape[1]} vs {oos_m.shape[1]}"
        )
    if is_m.shape[1] < 2:
        raise ValueError("PBO needs at least 2 trials to rank against")
    if n_blocks % 2 != 0 or n_blocks < 2:
        raise ValueError(f"n_blocks must be a positive even number, got {n_blocks}")

    matrix = np.vstack([is_m, oos_m])
    rows = (len(matrix) // n_blocks) * n_blocks
    if rows < n_blocks:
        raise ValueError(f"not enough rows ({len(matrix)}) for n_blocks={n_blocks}")
    blocks = np.array_split(matrix[len(matrix) - rows :], n_blocks)

    n_trials = matrix.shape[1]
    below_median = 0
    combos = list(combinations(range(n_blocks), n_blocks // 2))
    for chosen in combos:
        rest = [i for i in range(n_blocks) if i not in chosen]
        train = np.vstack([blocks[i] for i in chosen])
        test = np.vstack([blocks[i] for i in rest])
        winner = int(np.argmax(_column_sharpes(train)))
        oos_sharpes = _column_sharpes(test)
        rank = float((oos_sharpes <= oos_sharpes[winner]).sum())  # 1..n_trials
        relative = rank / (n_trials + 1.0)
        if relative <= 0.5:  # logit(relative) <= 0: winner at/below OOS median
            below_median += 1
    return below_median / len(combos)


# -- Combinatorial Purged Cross-Validation -----------------------------------


class CombinatorialPurgedCV:
    """Combinatorial CV with purging and an embargo — leakage-proof (I9).

    The sample is divided into ``n_groups`` contiguous groups; every
    combination of ``n_test_groups`` groups forms one fold's test set
    (``C(n_groups, n_test_groups)`` folds in total). Two guards make
    overlapping-label leakage impossible:

    - **Purge**: a training sample whose label window ``[t, label_time(t)]``
      overlaps any test group's window is dropped.
    - **Embargo**: training samples within ``embargo`` bars *after* the end of
      a test group are dropped (serial-correlation bleed).

    Deterministic: folds are a pure function of the inputs (I8).
    """

    def __init__(self, n_groups: int = 6, n_test_groups: int = 2, embargo: int = 0) -> None:
        """
        Args:
            n_groups: number of contiguous groups the sample is divided into.
            n_test_groups: groups per test set.
            embargo: default embargo, in bars, applied after each test group.
        """
        if n_test_groups < 1 or n_test_groups >= n_groups:
            raise ValueError(
                f"need 1 <= n_test_groups < n_groups, got {n_test_groups} of {n_groups}"
            )
        if embargo < 0:
            raise ValueError(f"embargo must be >= 0, got {embargo}")
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.embargo = embargo

    @property
    def n_folds(self) -> int:
        """Number of folds ``split`` yields."""
        return math.comb(self.n_groups, self.n_test_groups)

    def split(
        self,
        X: pd.DataFrame | pd.Series | np.ndarray,
        label_times: pd.Series | np.ndarray | None = None,
        embargo: int | None = None,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield ``(train_positions, test_positions)`` per combinatorial fold.

        Args:
            X: the sample (only its length/order matter).
            label_times: for each sample, the **position** (integer bar offset
                into ``X``) at which its label is fully known — e.g.
                ``arange(n) + horizon - 1`` for h-bar forward labels. Defaults
                to each sample's own position (point labels).
            embargo: bars to embargo after each test group; the constructor's
                value when omitted.

        Yields:
            Tuples of integer position arrays; train sets are purged and
            embargoed so no train label window overlaps a test window.

        Raises:
            ValueError: when the sample is shorter than ``n_groups``.
        """
        n = len(X)
        if n < self.n_groups:
            raise ValueError(f"sample of {n} is shorter than n_groups={self.n_groups}")
        emb = self.embargo if embargo is None else embargo
        if label_times is None:
            label_end = np.arange(n, dtype=float)
        else:
            label_end = np.asarray(label_times, dtype=float)
            if len(label_end) != n:
                raise ValueError("label_times must align 1:1 with X")

        bounds = np.linspace(0, n, self.n_groups + 1, dtype=int)
        groups = [np.arange(bounds[g], bounds[g + 1]) for g in range(self.n_groups)]
        positions = np.arange(n)

        for chosen in combinations(range(self.n_groups), self.n_test_groups):
            test_idx = np.concatenate([groups[g] for g in chosen])
            keep = np.ones(n, dtype=bool)
            keep[test_idx] = False
            for g in chosen:
                start = float(groups[g][0])
                end_label = float(label_end[groups[g]].max())
                # Purge: drop any train sample whose label window overlaps
                # [start, end_label] of this test group.
                overlap = (label_end >= start) & (positions.astype(float) <= end_label)
                keep[overlap] = False
                # Embargo: drop the `emb` bars immediately after the group.
                tail = groups[g][-1]
                keep[tail + 1 : tail + 1 + emb] = False
            yield positions[keep], np.sort(test_idx)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable configuration (pinned into manifests, I8)."""
        return {
            "n_groups": self.n_groups,
            "n_test_groups": self.n_test_groups,
            "embargo": self.embargo,
            "n_folds": self.n_folds,
        }
