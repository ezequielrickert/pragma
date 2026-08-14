# `generators/master_document.py`

## module

D12: the document that explains the other documents.

The decision behind it (`research/plan-generacion-de-documentos.md` H5)
was explicitly "both": keep generating every document separately, and
*also* write one that ties them together. Not one replacing the other -
someone who wants the API contract should open the API contract, and
someone opening `docs/` for the first time should not have to guess which
of ten files that is.

**Why it contains no LLM call.** The obvious temptation is to have the
model write a paragraph about what the application does. D1 already does
exactly that, at length, from the same graph. Two documents narrating the
same thing in different words is not twice the value - it is a
contradiction waiting to happen, and the reader has no way to know which
one is authoritative. This document answers a different question, "which
file do I open", and that question has a deterministic answer.

## MasterDocument

**Why it is not registered in `DOCUMENT_REGISTRY`.** Registering it would
make it schedulable among the ordinary documents - and it is the one
generator whose input is the other generators' *output*. Run in the middle
of the list, it would render an index of however many documents happened
to precede it, with no error and no missing file: silently wrong output,
which is the worst failure mode available. Keeping it out of the registry
makes that arrangement unrepresentable rather than merely discouraged.

The corollary is that it cannot be turned off in config. That is
intentional: it costs one file write and no model call, and a run whose
index is missing is harder to explain than one with an index nobody read.

## no-own-banner

An earlier revision rendered the coverage banner inside `generate`, which
double-printed it once the pipeline started applying the banner to every
Markdown document. The banner now lives in exactly one place
(`pipeline._with_banner`) and this generator produces its body only -
the same rule every other Markdown document follows.
