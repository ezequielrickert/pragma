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

Then run:

```bash
# No server to start - graph_store: ladybug (or memory) is embedded, nothing
# to run before the crawl itself. On disk it lands in data/sites/<slug>.lbdb.
#eze: 
python3 cli.py https://example.com
#juli:
python cli.py https://example.com
```
