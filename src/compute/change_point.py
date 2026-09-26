"""
src/compute/change_point.py

Pettitt (1979) test for a single change point in the level of a series.

    U_t = sum over i <= t, j > t of sign(x_i - x_j),   t = 1 .. n-1
    K   = max |U_t|,  break after the t that gives K
    p   ~ 2 exp(-6 K^2 / (n^3 + n^2))   (approximation, capped at 1)

Pettitt, A. N. (1979). A non-parametric approach to the change-point problem.
Journal of the Royal Statistical Society, Series C, 28(2), 126-135.
https://doi.org/10.2307/2346729

Note: a steady trend also gives a large K, so a small p means "the level is not the
same all through", not proof of a sudden jump. Compare the means before and after.
"""

import numpy as np


def pettitt_test(values):
    """Pettitt change-point test on a 1-D sequence (NaNs not allowed).

    Returns a dict:
      K           test statistic, max |U_t|
      split       number of values before the break (the break is between
                  values[split - 1] and values[split])
      p           approximate two-sided p-value
      mean_before, mean_after   means of the two segments
      n           series length
    """
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 3:
        raise ValueError("pettitt_test needs a 1-D series of at least 3 values")
    if np.isnan(x).any():
        raise ValueError("pettitt_test does not accept NaN")
    n = len(x)
    signs = np.sign(x[:, None] - x[None, :])  # signs[i, j] = sign(x_i - x_j)
    u = np.array([signs[:t, t:].sum() for t in range(1, n)])
    t_best = int(np.argmax(np.abs(u)))  # first t with the largest |U_t|
    k = float(abs(u[t_best]))
    split = t_best + 1
    p = min(1.0, 2.0 * np.exp(-6.0 * k ** 2 / (n ** 3 + n ** 2)))
    return {"K": k, "split": split, "p": float(p),
            "mean_before": float(x[:split].mean()), "mean_after": float(x[split:].mean()),
            "n": n}
