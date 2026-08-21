# `core/documents.py`

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

Since docs/adr/0030 (the multi-file/kind-tagged output contract, ticket
#95), this module also carries `DocumentKind`/`DocumentOutput`: what
`CONTEXT.md`'s source/view/projection/rule-catalog taxonomy looks like as
real types, not just a glossary entry.

## DocumentKind

The four terms `CONTEXT.md`'s glossary already defined for the pipeline,
as a `Literal` rather than a bare `str`: a generator that returns
`kind="veiw"` fails at the type-checker, not three documents later when
something reads `ProducedDocument.kind` expecting one of the four.

## DocumentOutput

One physical file. `filename` carries no extension on purpose -
`DocumentNaming.path_for` (`generators/pipeline.py`) owns wrapping it with
the run's slug/timestamp and appending `extension`, the one place every
document's filename is built, unchanged by this contract.

## ProducedDocument

What the pipeline hands back per *file* now, not per generator - a
source/view split generator (`coverage`, `export`) produces two of these
from one registry entry. Deliberately carries `title`/`purpose` *copied*
from the generator rather than a reference to the generator itself: by
the time the master document runs, what matters is what was written, not
what could have written it. `kind` and `checksum` are computed once, by
`generators/pipeline.py::_write_document`, from the bytes actually
written to disk - never invented by the generator itself, which has no
access to the final path or content-after-banner.

## DocumentRequest

One object rather than several positional arguments, so adding something
a future generator needs (a config knob, a second store) doesn't change
every existing generator's signature. Frozen, because a generator reading
its request must not be able to affect the next generator's.

`settings` is a plain dict rather than typed fields for a deliberate
tradeoff: it means a generator can read a knob `DocumentRequest` has never
heard of, at the cost of no type checking on the key. The alternative -
a typed field per document-specific setting - would put every document's
tuning knobs in a shared class that most documents ignore.

## ProducedDocument.filename

Added in ticket #109 (docs/adr/0015): the raw `DocumentOutput.filename` a
generator passed in, before `DocumentNaming.path_for` wraps it with the
run's slug and timestamp. `manifest.json`/`llms.txt` need this stable
identifier to key their own lookups on (a document's external-standard
`format`, its place in the resolution order) - `path` alone can't be
reliably reversed back into it, since both the slug and the filename can
contain `_`/`.`.

## DocumentRequest.produced

Empty for every ordinary generator and filled only for the master
document. This is why the master document is not in `DOCUMENT_REGISTRY`
(see `master_document.md`): if it could be scheduled among the ordinary
generators, `produced` would hold only the documents that happened to run
before it, and the resulting index would be silently incomplete rather
than obviously broken.

## DocumentGenerator

An `ABC`, `generate` an `@abstractmethod` - a generator that forgets to
implement it fails at class-definition time, not the first time the
pipeline tries to call it. Takes no constructor arguments.

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

Returns content and never writes to disk - the pipeline owns writing,
which is what lets it apply the coverage banner uniformly and lets tests
call a generator directly without a filesystem.

Two accepted return shapes, both still supported: a bare `str` (the
original contract - one Markdown/JSON view, unchanged for the ~17
generators that only ever needed this), or a `Tuple[DocumentOutput, ...]`
for a generator that owns more than one file (a source/view split, or
more). `outputs()` is what normalizes between them; `generate()` itself
never has to know which shape a caller ultimately wants.

## outputs

The one place `generate()`'s two accepted return shapes get wrapped into
the single shape every real caller (`generators/pipeline.py`) actually
consumes - a bare string becomes one `DocumentOutput` with `kind="view"`
and `self.extension`, so a single-file generator needs no code change to
keep working under the multi-file contract.
