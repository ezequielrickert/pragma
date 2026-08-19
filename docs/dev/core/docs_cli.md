# core/docs_cli.py

## module

`pragma docs` command: parse its args, generate documents from an
existing site DB, report the result.

## parse_docs_args

A site, not a URL: `pragma docs` reads a `pragma static` run already on
disk, so there is nothing here to navigate to. No `--fresh` flag, same
reasoning as `pragma dynamic` - purging the graph store's recorded state
before a read-only pass would defeat the entire point of reading it.

## run_docs_command

`pragma docs <site>`: project, then generate - see `DocsEngine` for what
that means in practice. Prints "master first, then the rest" the same
way `cli.py::_print_documents` does, but as its own small inline loop
rather than importing that function - `core/docs_cli.py` importing
top-level `cli.py` would run against this project's layering, the
reverse of every other dependency direction here.
