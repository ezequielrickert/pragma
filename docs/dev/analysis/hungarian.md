# analysis/hungarian.py

## module

The Hungarian algorithm (Kuhn-Munkres) - optimal bipartite assignment,
O(n^3). Hand-rolled rather than pulling in scipy: scipy sits in this
project's virtualenv only as some other dependency's transitive pull, never
declared in `requirements.txt`, and composite/subtree matching's own design
doc (issue #132) frames this as "cubic in a tiny n" - small enough that a
plain, dependency-free implementation is the right size for the problem.

## min_cost_assignment

The minimum-total-cost 1:1 assignment over a rectangular cost matrix - one
entry per matched pair, `min(rows, cols)` pairs long. Pads the smaller side
up to a square matrix with a cost of `0` before running `_kuhn_munkres`; a
real edge here is a similarity turned into a cost (`-similarity`, always
`<= 0`), so a real match is never worse than a padding one.

## _kuhn_munkres

Minimum-cost perfect matching on a *square* cost matrix - the
potentials/shortest-augmenting-path formulation of the Hungarian algorithm,
verified against exhaustive brute-force search on 200 random matrices
while building this (`tests/test_hungarian.py` pins the deterministic
cases; the randomized check itself isn't part of the suite, since it isn't
a regression pin so much as the one-time correctness proof for a from-
scratch implementation).
