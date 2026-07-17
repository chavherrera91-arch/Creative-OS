"""Reproducibility helpers (invariant I8).

``assert_reproducible`` re-runs a research function and asserts the results are
identical — the executable definition of "a fixed decision/backtest replays
identically". It is used by the test suite and available to any research code
that wants to self-check.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["assert_identical", "assert_reproducible"]


def assert_identical(a: Any, b: Any, path: str = "result") -> None:
    """Recursively assert that two research outputs are identical.

    Handles pandas objects, numpy arrays, mappings, sequences, floats (NaN-safe)
    and objects exposing ``as_dict()`` (the house serialisation convention).

    Raises:
        AssertionError: at the first differing leaf, naming its path.
    """
    if hasattr(a, "as_dict") and hasattr(b, "as_dict"):
        assert_identical(a.as_dict(), b.as_dict(), path)
        return
    if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
        assert isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame), f"{path}: type diff"
        pd.testing.assert_frame_equal(a, b)
        return
    if isinstance(a, pd.Series) or isinstance(b, pd.Series):
        assert isinstance(a, pd.Series) and isinstance(b, pd.Series), f"{path}: type diff"
        pd.testing.assert_series_equal(a, b)
        return
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=f"{path}: array diff")
        return
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        assert set(a) == set(b), f"{path}: key diff {set(a) ^ set(b)}"
        for key in a:
            assert_identical(a[key], b[key], f"{path}.{key}")
        return
    if (
        isinstance(a, Sequence)
        and isinstance(b, Sequence)
        and not isinstance(a, (str, bytes))
        and not isinstance(b, (str, bytes))
    ):
        assert len(a) == len(b), f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            assert_identical(x, y, f"{path}[{i}]")
        return
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return
    assert a == b, f"{path}: {a!r} != {b!r}"


def assert_reproducible(fn: Callable[..., Any], *args: Any, runs: int = 2, **kwargs: Any) -> Any:
    """Run ``fn`` ``runs`` times and assert every result is identical (I8).

    Args:
        fn: a zero-side-effect research function (decision, backtest, ...).
        *args: positional arguments passed to every run.
        runs: how many times to execute ``fn`` (>= 2).
        **kwargs: keyword arguments passed to every run.

    Returns:
        The result of the first run, for further assertions.
    """
    assert runs >= 2, "assert_reproducible needs at least two runs"
    first = fn(*args, **kwargs)
    for _ in range(runs - 1):
        assert_identical(first, fn(*args, **kwargs))
    return first
