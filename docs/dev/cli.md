# `cli.py`

## main

Bare `python3 cli.py` from a real terminal launches the interactive
menu app (navigate between analyzing a URL and configuring the
pipeline, no flags needed). `python3 cli.py config` jumps straight
to the setup wizard. Any other invocation (a bare URL, unrecognized
flags) errors, naming the real subcommands - the Legacy Engine's own
bare-URL dispatch (a fused crawl+synthesize pass run directly) was
retired along with `core/engine.py` itself (issue #242, subsumes issue
#222): every invocation now names the phase it wants.

## _subcommands

The single source of truth `main()`'s dispatch table and its no-match
error message both read from, so a subcommand added to one can't drift
out of sync with the other.
