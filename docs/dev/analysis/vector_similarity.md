# analysis/vector_similarity.py

## module

Cosine similarity over the plain `list[float]` vectors this package's
matching modules (`leaf_feature_vector.py`, `composite_matching.py`)
produce - a tiny, dependency-free stand-in for what `QUERY_VECTOR_INDEX`
does against a real Kùzu `FLOAT[n]` column once one exists (issue #139).

## cosine_similarity

`0.0` for either zero vector rather than a `ZeroDivisionError` - two
vectors with nothing in them share no genuine similarity signal to report.
