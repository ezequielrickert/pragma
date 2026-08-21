"""Unit tests for hungarian.py's optimal-assignment implementation."""
from analysis.hungarian import min_cost_assignment


def _total_cost(cost, assignment):
    return sum(cost[r][c] for r, c in assignment)


def test_a_known_square_matrix_matches_its_known_optimal_assignment():
    cost = [[4, 1, 3], [2, 0, 5], [3, 2, 2]]
    assignment = min_cost_assignment(cost)

    assert len(assignment) == 3
    assert _total_cost(cost, assignment) == 5


def test_every_row_and_column_is_used_at_most_once():
    cost = [[9, 1, 2], [3, 8, 1], [4, 2, 7]]
    assignment = min_cost_assignment(cost)

    rows = [r for r, _ in assignment]
    cols = [c for _, c in assignment]
    assert len(rows) == len(set(rows))
    assert len(cols) == len(set(cols))


def test_a_rectangular_matrix_matches_only_the_smaller_side():
    # 2 rows, 3 columns - only 2 pairs possible, one column left unmatched.
    cost = [[1, 5, 9], [9, 1, 5]]
    assignment = min_cost_assignment(cost)

    assert len(assignment) == 2
    assert _total_cost(cost, assignment) == 2  # (0,0)+(1,1) = 1+1


def test_an_empty_matrix_returns_no_assignment():
    assert min_cost_assignment([]) == []


def test_a_single_cell_matrix_assigns_it():
    assert min_cost_assignment([[7.0]]) == [(0, 0)]
