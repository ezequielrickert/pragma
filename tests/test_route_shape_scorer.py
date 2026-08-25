"""Regression coverage for `RouteShapeNoveltyScorer`
(spiders/orchestration/route_shape_scorer.py) - issue #247: the url_scorer
`PragmaBestFirstStrategy` orders its priority queue by.
"""
from spiders.orchestration.route_shape_scorer import RouteShapeNoveltyScorer


def test_an_unvisited_route_shape_scores_at_the_maximum():
    scorer = RouteShapeNoveltyScorer(route_shape_visits={}, max_visits_per_route_shape=1)
    assert scorer.score("http://example.com/page") == 1.0


def test_a_route_shape_already_at_the_cap_scores_zero():
    visits = {"example.com/o/{token}": 1}
    scorer = RouteShapeNoveltyScorer(visits, max_visits_per_route_shape=1)
    assert scorer.score("http://example.com/o/aB1cD2eF3gH4iJ5kL6mN") == 0.0


def test_a_route_shape_partway_to_the_cap_scores_between_zero_and_one():
    visits = {"example.com/o/{token}": 1}
    scorer = RouteShapeNoveltyScorer(visits, max_visits_per_route_shape=4)
    assert scorer.score("http://example.com/o/aB1cD2eF3gH4iJ5kL6mN") == 0.75


def test_scoring_reads_the_live_dict_not_a_snapshot_taken_at_construction():
    """PragmaBestFirstStrategy hands the scorer its own _route_shape_visits
    by reference so scores stay current as the crawl counts visits - a
    scorer that copied the dict at construction would score every URL as
    if nothing had been visited yet."""
    visits = {}
    scorer = RouteShapeNoveltyScorer(visits, max_visits_per_route_shape=1)
    assert scorer.score("http://example.com/page") == 1.0

    visits["example.com/page"] = 1
    assert scorer.score("http://example.com/page") == 0.0


def test_a_cap_of_zero_never_scores_a_url_as_novel():
    scorer = RouteShapeNoveltyScorer(route_shape_visits={}, max_visits_per_route_shape=0)
    assert scorer.score("http://example.com/page") == 0.0
