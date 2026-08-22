# analysis/deterministic_hashing.py

## module

One-hot/multi-hot encoding into a fixed-size bucket, by deterministic
hash - shared by `leaf_feature_vector.py` and `tailwind_semantic_classes.py`
(issue #168 pulled this out of both; before it, each module carried its
own identical copy). `hashlib.sha1`, never Python's built-in `hash()` -
process-randomized by `PYTHONHASHSEED`, not reproducible across runs.

## hash_one_hot

One field's value, hashed into one of `bucket_count` slots. An empty
string hashes like any other value, so "this field is absent" collides
into one shared bucket rather than being dropped - lacking a value is
itself a signal, not noise.

## hash_multi_hot

A *set* of values, each hashed and OR'd into one binary vector -
membership, independent of order or repeats, is what determines this
slice. `css_class`'s old raw encoding (before issue #168) and
`tailwind_semantic_classes.py`'s per-concept property hashes both use
this.
