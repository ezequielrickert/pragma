"""The Hungarian algorithm (Kuhn-Munkres) - optimal bipartite assignment,
O(n^3). Hand-rolled rather than pulling in scipy (`scipy.optimize.
linear_sum_assignment` would do this in one call): scipy sits in this
project's virtualenv only as some other dependency's transitive pull, never
declared in `requirements.txt`, and composite/subtree matching's own design
doc (issue #132) frames this as "cubic in a tiny n, composites are tens of
children ... not hundreds" - small enough that a plain, dependency-free
implementation is the right size for the problem, not a shortcut.

Used by `composite_matching.py` to find the best 1:1 correspondence between
two composites' children - the assignment itself *is* the child-to-child
correspondence ("which nav link on page A paired with which on page B"),
not just a number.

Details: docs/dev/analysis/hungarian.md#module
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

_INFINITY = float("inf")


def min_cost_assignment(cost: Sequence[Sequence[float]]) -> List[Tuple[int, int]]:
    """The minimum-total-cost 1:1 assignment over a rectangular `cost`
    matrix (rows need not equal columns) - `[(row, col), ...]`, one entry
    per matched pair, `min(len(cost), len(cost[0]))` pairs long. A row or
    column past that count is left unmatched, exactly the "count mismatch"
    case the composite score's coverage weighting depends on.

    Internally pads the smaller side up to a square matrix with a cost of
    `0` - the algorithm below only assigns a real row/column to a padding
    one when there is no real counterpart left, since every real edge
    here is a similarity turned into a cost (`-similarity`, `<= 0`), so a
    real match is never worse than a padding one.
    Details: docs/dev/analysis/hungarian.md#min_cost_assignment
    """
    rows = len(cost)
    cols = len(cost[0]) if rows else 0
    if rows == 0 or cols == 0:
        return []

    size = max(rows, cols)
    padded = [
        [cost[r][c] if r < rows and c < cols else 0.0 for c in range(size)]
        for r in range(size)
    ]
    row_for_col = _kuhn_munkres(padded)
    return [
        (row, col)
        for col, row in enumerate(row_for_col)
        if row < rows and col < cols
    ]


def _kuhn_munkres(cost: List[List[float]]) -> List[int]:
    """Minimum-cost perfect matching on a *square* cost matrix - the
    potentials/shortest-augmenting-path formulation of the Hungarian
    algorithm. Returns `row_for_col[j]`: the row assigned to column `j`.
    1-indexed internally (the classic formulation's own convention,
    `0` reserved as an unassigned sentinel), translated back to 0-indexed
    on return.
    Details: docs/dev/analysis/hungarian.md#_kuhn_munkres
    """
    n = len(cost)
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    row_for_col = [0] * (n + 1)
    parent_col = [0] * (n + 1)

    for i in range(1, n + 1):
        row_for_col[0] = i
        current_col = 0
        min_to_col = [_INFINITY] * (n + 1)
        visited = [False] * (n + 1)
        while True:
            visited[current_col] = True
            current_row = row_for_col[current_col]
            delta = _INFINITY
            next_col = -1
            for col in range(1, n + 1):
                if visited[col]:
                    continue
                reduced_cost = cost[current_row - 1][col - 1] - u[current_row] - v[col]
                if reduced_cost < min_to_col[col]:
                    min_to_col[col] = reduced_cost
                    parent_col[col] = current_col
                if min_to_col[col] < delta:
                    delta = min_to_col[col]
                    next_col = col
            for col in range(n + 1):
                if visited[col]:
                    u[row_for_col[col]] += delta
                    v[col] -= delta
                else:
                    min_to_col[col] -= delta
            current_col = next_col
            if row_for_col[current_col] == 0:
                break
        # Walk the augmenting path back to the root, flipping each edge.
        while current_col:
            prev_col = parent_col[current_col]
            row_for_col[current_col] = row_for_col[prev_col]
            current_col = prev_col

    return [row_for_col[col] - 1 for col in range(1, n + 1)]
