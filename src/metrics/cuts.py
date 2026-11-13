"""Cuts of the per-problem table (research R6; FR-012): an empty list filters nothing."""

import pandas as pd


class CutError(ValueError):
    """A cut that cannot give a metric (for example, a single problem)."""


def apply(
    per_problem: pd.DataFrame,
    *,
    macrocategorias=(),
    ratings=(),
    statuses=(),
    sets=(),
    scenarios=(),
    problems=(),
    detected_wa: pd.DataFrame | None = None,
):
    """The rows of the cut (and, if given, the detected WAs of the same problems and sets)."""
    mask = pd.Series(True, index=per_problem.index)
    for column, allowed in (
        ("macrocategoria", macrocategorias),
        ("rating", ratings),
        ("status", statuses),
        ("set", sets),
        ("scenario", scenarios),
        ("problem", problems),
    ):
        if allowed:
            mask &= per_problem[column].isin(list(allowed))
    cut = per_problem[mask]
    if cut["problem"].nunique() == 1:
        raise CutError("a cut with a single problem has no metric; look at it in the dashboard")
    if detected_wa is None:
        return cut
    keys = cut[["set", "scenario", "problem"]].drop_duplicates()
    return cut, detected_wa.merge(keys, on=["set", "scenario", "problem"])
