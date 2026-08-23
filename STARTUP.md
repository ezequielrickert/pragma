# Startup

Setup, once per environment:

```bash
pip install -r requirements.txt
python -m playwright install
```

On Windows, also this - the `ladybug` wheel does not ship the native library, and
without it every `graph_store` fails and `pytest` cannot collect. Tag must match
the `ladybug==` pin in `requirements.txt`:

```powershell
$version = "v0.19.1"
$pkg  = python -c "import ladybug, pathlib; print(pathlib.Path(ladybug.__file__).parent)"
$dlls = python -c "import sys, pathlib; print(pathlib.Path(sys.base_prefix) / 'DLLs')"
$tmp  = Join-Path $env:TEMP "lbug"

New-Item -ItemType Directory -Force $tmp | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile "$tmp\lbug.zip" `
  "https://github.com/LadybugDB/ladybug/releases/download/$version/liblbug-windows-x86_64.zip"
Expand-Archive "$tmp\lbug.zip" -DestinationPath $tmp -Force

Copy-Item "$tmp\lbug_shared.dll" $pkg -Force
Copy-Item "$dlls\libcrypto-3.dll" (Join-Path $pkg "libcrypto-3-x64.dll") -Force
Copy-Item "$dlls\libssl-3.dll"    (Join-Path $pkg "libssl-3-x64.dll")    -Force

python -c "import ladybug as lb; lb.Connection(lb.Database('')); print('engine OK')"
```

Redo it after recreating the venv: it lands in `site-packages`.

Then run one of these. No server to start first - `graph_store: ladybug` (or
`memory`) is embedded, nothing to run before the crawl itself; on disk it
lands in `data/sites/<slug>.lbdb`. Interpreter name varies by machine (eze:
`python3`, juli: `python`) - the examples below use `python`, swap as needed.

Every command past the first refers to a site by its **slug** - the host
part of the URL, as `static` first wrote it (`https://example.com` ->
`example.com`).

## One shot: crawl a site and generate everything

```bash
# Static-crawl the site, cluster components into families, run the dynamic
# (click/fill) pass, then generate every document + the dashboard - all in
# one run.
python cli.py https://example.com
```

## Or, phase by phase

Useful to inspect state between phases, or re-run just one with different
flags - state persists in `data/sites/<slug>.lbdb` between runs (pass
`--fresh` to purge it and start over).

```bash
# 1. Scout-only crawl: HTML/CSS/routes into the graph store, no clicking or
#    filling anything.
python cli.py static https://example.com

# 2. Group the discovered components into reusable families (LLM-narrated).
python cli.py cluster example.com

# 3. Interact: click/fill, resuming from static's frontier and sampling per
#    family instead of hitting every instance.
python cli.py dynamic https://example.com

# static -> cluster -> dynamic chained in one call - stops there, never
# generates documents (that stays the separate `docs` step below).
python cli.py crawl https://example.com
```

## Documents + dashboard, once a site is crawled

```bash
# Generate every document + the dashboard from an already-crawled site - no
# re-crawl. Faster than the one-shot above when only generator code changed.
python cli.py docs example.com

# The dashboard always lands at <out_dir>/dashboard/index.html (out_dir
# defaults to data/output, override with --out). Static HTML, including the
# Graph card (export.json's graph, explorable) - open it directly in a
# browser, no server needed.
```

## Interactive editor + chat, once documents exist

A separate, editable local tool - not the static dashboard above. Serves the
site's already-generated documents with a raw-text editor (plus real forms
for some, e.g. `tokens.json`'s color picker) and a chat panel grounded in
each document's real citations.

```bash
# Defaults to http://127.0.0.1:5050 (--host/--port to change).
python cli.py interactive example.com

# --agent local needs `python cli.py config` run once (API key/model) for
# real chat replies; the default (or explicit --agent mock) still runs the
# editor/chat end to end, just with canned stub replies.
python cli.py interactive example.com --agent local
```

Stop it with Ctrl+C, or the in-chat "finalizar" button - either shuts the
server down cleanly. Chat history is in-memory only, gone once the session
ends.
