# `src/core/documents.py`

## module

The document pipeline's contracts, kept out of `interfaces.py` on purpose.

`interfaces.py` holds what the *crawl* is built from - `Agent` and
`GraphStore`, the two things a plugin can implement to change how Pragma
crawls or stores. Document generation consumes both but is a separate
concern: a new document never changes how crawling works, and a new
`GraphStore` backend never changes what documents exist. Splitting them
also keeps `interfaces.py` from drifting further past the 300-line mark
this project treats as a split signal - the same reason `data_contracts.py`
was carved out of it earlier.

## ProducedDocument

What the pipeline hands back per document, and what the master document
renders. Deliberately carries `title` and `purpose` *copied* from the
generator rather than a reference to the generator itself: by the time
the master document runs, what matters is what was written, not what
could have written it. A plain record is also trivially serializable into
the run manifest, which a live generator object is not.

## DocumentRequest

One object rather than four positional arguments, so adding something a
future generator needs (a config knob, a second store) doesn't change
every existing generator's signature. Frozen, because a generator reading
its request must not be able to affect the next generator's.

`settings` is a plain dict rather than typed fields for a deliberate
tradeoff: it means a generator can read a knob `DocumentRequest` has never
heard of, at the cost of no type checking on the key. The alternative -
a typed field per document-specific setting - would put every document's
tuning knobs in a shared class that most documents ignore.

## DocumentRequest.produced

Empty for every ordinary generator and filled only for the master
document. This is why the master document is not in `DOCUMENT_REGISTRY`
(see `master_document.md`): if it could be scheduled among the ordinary
generators, `produced` would hold only the documents that happened to run
before it, and the resulting index would be silently incomplete rather
than obviously broken.

## DocumentGenerator

A plain base class, not an ABC with `@abstractmethod`, and it takes no
constructor arguments.

**Why no constructor arguments.** `DOCUMENT_REGISTRY.create(name)` has to
be able to build any generator without knowing which one it asked for. If
generators took their dependencies at construction time, the pipeline
would need a per-generator wiring table - exactly the hardcoded block in
`Engine` that this whole design exists to delete. Everything a generator
needs arrives in `generate`'s request instead.

**Why `name` is one string for three jobs** (registry key, config name,
manifest key): so a document cannot end up called three different things
in three places, and so `pipeline.document_path` can build the filename
from the same string.

## generate

Returns text and never writes to disk. The pipeline owns writing, which
is what lets it apply the coverage banner uniformly and lets tests call a
generator directly without a filesystem.
