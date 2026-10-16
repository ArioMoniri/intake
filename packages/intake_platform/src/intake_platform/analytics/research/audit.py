"""INT-490 — the check across views: no small group is recoverable by arithmetic.

LD-06 ``admin_analytics.conditions.across_views``: *"a withheld cell can still
be recovered by subtraction from a wider aggregate over the same population,
so step 2 needs … a check across views"*. This is that check, and it asks the
general question rather than a list of known attacks:

    Is there ANY group of people, holding between 1 and k-1 of them, whose
    size can be computed by adding and subtracting the counts that are shown?

**Why the question is answerable.** Every shown count is the size of a set of
people. Group the people into *classes* by exactly which shown cells they
belong to: two people in one class are interchangeable to anyone holding the
release, so any count a reader can compute is a sum over whole classes. A
reader can compute the size of a union of classes exactly when its indicator
vector lies in the row space of the cells × classes incidence matrix. So the
check is: no 0/1 vector in that row space has a weight between 1 and k-1.

**How it is searched.** Order the classes with every class of k or more first.
A recoverable set smaller than k cannot contain one of those, so only the part
of the row space that vanishes on them matters; in reduced row-echelon form
those are exactly the rows whose pivot is a small class, and a vector in it is
fixed by which of those rows it takes. The search enumerates those choices,
pruned by size (the pivots it takes are members, so their sizes alone bound
the total below k).

**Fail-closed in two places.** Arithmetic is exact modulo the Mersenne prime
2^61-1: a vector in the rational row space is in the modular one too, so the
modular test can only over-report — never miss. And the search has a node
budget; running out of it is reported as a violation, so a release the check
cannot prove safe is treated as unsafe.

Zero is not protected, here or in INT-171: a materialised INT-171 view already
tells its reader that an absent group is empty. A shown view whose population
is empty is refused upstream, exactly like a thin one.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Final

__all__ = ["NODE_BUDGET", "Violation", "find_recoverable_small_set"]

_PRIME: Final = (1 << 61) - 1

#: How many partial selections the search may visit before it gives up and
#: reports the release unsafe. A count of work, not a privacy parameter.
NODE_BUDGET: Final = 200_000


@dataclass(frozen=True)
class Violation:
    """The shown cells whose counts, added and subtracted, recover a small
    group — including the cells subtracted away, which do not contain it. The
    release withholds one view among them and asks again."""

    cells: frozenset[Hashable]
    #: the search ran out of budget rather than finding a group
    exhausted: bool


class _Exhausted(Exception):
    pass


def _classes(
    cells: Mapping[Hashable, frozenset[Hashable]],
) -> dict[frozenset[Hashable], int]:
    signature: dict[Hashable, set[Hashable]] = {}
    for cell, members in cells.items():
        for member in members:
            signature.setdefault(member, set()).add(cell)
    sizes: dict[frozenset[Hashable], int] = {}
    for cells_of_member in signature.values():
        key = frozenset(cells_of_member)
        sizes[key] = sizes.get(key, 0) + 1
    return sizes


def _order(sizes: Mapping[frozenset[Hashable], int], k: int) -> list[frozenset[Hashable]]:
    def sort_key(signature: frozenset[Hashable]) -> tuple[int, int, str]:
        size = sizes[signature]
        return (0 if size >= k else 1, -size, repr(sorted(map(repr, signature))))

    return sorted(sizes, key=sort_key)


_Vector = dict[int, int]


def _axpy(target: _Vector, coefficient: int, source: _Vector) -> None:
    """``target -= coefficient * source``, modulo the prime, dropping zeros."""
    for column, value in source.items():
        updated = (target.get(column, 0) - coefficient * value) % _PRIME
        if updated:
            target[column] = updated
        else:
            target.pop(column, None)


def _rref(rows: list[_Vector]) -> dict[int, tuple[_Vector, _Vector]]:
    """Fully reduced row-echelon basis, keyed by pivot column, each row with
    the combination of input rows that produces it. A row's pivot is its first
    non-zero column, which stays true as later pivots are cleared."""
    basis: dict[int, tuple[_Vector, _Vector]] = {}
    for index, raw in enumerate(rows):
        row, combination = dict(raw), {index: 1}
        for pivot in [column for column in row if column in basis]:
            coefficient = row.get(pivot, 0)
            if coefficient:
                _axpy(row, coefficient, basis[pivot][0])
                _axpy(combination, coefficient, basis[pivot][1])
        if not row:
            continue
        pivot = min(row)
        inverse = pow(row[pivot], _PRIME - 2, _PRIME)
        row = {column: value * inverse % _PRIME for column, value in row.items()}
        combination = {i: value * inverse % _PRIME for i, value in combination.items()}
        for other_row, other_combination in basis.values():
            coefficient = other_row.get(pivot, 0)
            if coefficient:
                _axpy(other_row, coefficient, row)
                _axpy(other_combination, coefficient, combination)
        basis[pivot] = (row, combination)
    return basis


def _search(
    rows: list[tuple[int, _Vector]], sizes: list[int], k: int, budget: int
) -> tuple[int, ...] | None:
    """The pivots of a 0/1 vector of weight 1..k-1, or ``None``."""
    visited = 0

    def visit(
        start: int, acc: _Vector, chosen: int, taken: tuple[int, ...]
    ) -> tuple[int, ...] | None:
        nonlocal visited
        for index in range(start, len(rows)):
            pivot, row = rows[index]
            if chosen + sizes[pivot] >= k:
                continue
            visited += 1
            if visited > budget:
                raise _Exhausted
            combined = dict(acc)
            _axpy(combined, _PRIME - 1, row)  # combined += row
            picked = (*taken, index)
            if combined and all(value == 1 for value in combined.values()):
                if sum(sizes[column] for column in combined) < k:
                    return picked
            found = visit(index + 1, combined, chosen + sizes[pivot], picked)
            if found is not None:
                return found
        return None

    return visit(0, {}, 0, ())


def find_recoverable_small_set(
    cells: Mapping[Hashable, frozenset[Hashable]], *, k: int, budget: int = NODE_BUDGET
) -> Violation | None:
    """``None`` when no group of 1 to ``k``-1 people is recoverable from
    ``cells`` (shown cell -> the people it counts), else the cells involved."""
    sizes_by_signature = _classes(cells)
    order = _order(sizes_by_signature, k)
    large = sum(1 for signature in order if sizes_by_signature[signature] >= k)
    if large == len(order):
        return None
    sizes = [sizes_by_signature[signature] for signature in order]
    column_of = {signature: index for index, signature in enumerate(order)}
    keys = list(cells)
    rows = [{column_of[s]: 1 for s in order if cell in s} for cell in keys]
    basis = _rref(rows)
    small_rows = sorted(
        ((pivot, vector) for pivot, (vector, _) in basis.items() if pivot >= large),
        key=lambda item: (-sizes[item[0]], item[0]),
    )
    if not small_rows:
        return None
    try:
        picked = _search(small_rows, sizes, k, budget)
    except _Exhausted:
        touched = {cell for signature in order[large:] for cell in signature}
        return Violation(cells=frozenset(touched), exhausted=True)
    if picked is None:
        return None
    combination: _Vector = {}
    for index in picked:
        _axpy(combination, _PRIME - 1, basis[small_rows[index][0]][1])
    return Violation(cells=frozenset(keys[i] for i in combination), exhausted=False)
