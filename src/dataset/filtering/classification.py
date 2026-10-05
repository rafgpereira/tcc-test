"""Macro-category of a problem by a FIXED priority (spec FR-006, FR-007; methodology 1.3).

1st ``estrutural_otimizacao`` (dp, binary search, sortings), 2nd ``matematica`` (math),
3rd ``logica_direta`` (implementation, strings, greedy). The most specific tag wins, and only the
tags of these lists count. The result never depends on the order of the tags.
"""

from collections.abc import Iterable

from dataset.schemas.common import Macrocategoria

_STRUCTURAL = frozenset({"dp", "binary search", "sortings"})
_MATH = frozenset({"math"})
_DIRECT = frozenset({"implementation", "strings", "greedy"})


def classify(tags: Iterable[str]) -> Macrocategoria:
    """Return the macro-category of ``tags``; ``ValueError`` when no allowed tag is present."""
    present = set(tags)
    if present & _STRUCTURAL:
        return Macrocategoria.ESTRUTURAL_OTIMIZACAO
    if present & _MATH:
        return Macrocategoria.MATEMATICA
    if present & _DIRECT:
        return Macrocategoria.LOGICA_DIRETA
    raise ValueError(f"no allowed tag in {sorted(present)}: the problem has no macro-category")
