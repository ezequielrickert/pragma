# Startup

```bash
# No server to start - graph_store: ladybug (or memory) is embedded, nothing
# to run before the crawl itself. On disk it lands in data/sites/<slug>.lbdb.
#eze: 
python3 cli.py https://example.com
#juli:
python cli.py https://example.com
```

## Windows: Ladybug needs a native library the wheel does not ship

Symptom - one of these, depending on which backend gets tried first:

```
RuntimeError: Could not find lbug C API shared library. Set LBUG_C_API_LIB_PATH
or download a shared lib (e.g. run LBUG_LIB_KIND=shared bash scripts/download_lbug.sh).
```
```
ImportError: DLL load failed while importing _lbug: The specified module could not be found.
```

Either one means every `graph_store` fails, `memory` included, and `pytest` cannot
even collect - `conftest.py` imports `core.bootstrap`, which imports the store.

**Why `pip install` is not enough.** The Windows wheel ships `_lbug.lib` (static)
and a pybind `_lbug.*.pyd`, and neither backend loads without `lbug_shared.dll`,
which is a separate download from the project's own release. Nothing about that is
in `requirements.txt`, because it is not a Python dependency.

**Why setting `LBUG_C_API_LIB_PATH` alone does not fix it**, even though the error
message suggests it: the loader finds the DLL and then fails on its dependencies
(`FileNotFoundError: ... or one of its dependencies`). `lbug_shared.dll` needs
OpenSSL 3 as `libcrypto-3-x64.dll` / `libssl-3-x64.dll`, and `ctypes.CDLL` with an
absolute path does not add that path to the search order for the library's *own*
imports. Putting all three files next to the package is what works.

CPython bundles the same OpenSSL 3 libraries under its own names
(`libcrypto-3.dll` / `libssl-3.dll`), so they only need copying, not installing.
The MSVC runtime (`msvcp140`, `vcruntime140`, `vcruntime140_1`) is normally
already present.

```powershell
# The release tag MUST match the version pinned in requirements.txt (ladybug==0.19.1).
$version = "v0.19.1"
$pkg  = python -c "import ladybug, pathlib; print(pathlib.Path(ladybug.__file__).parent)"
$dlls = python -c "import sys, pathlib; print(pathlib.Path(sys.base_prefix) / 'DLLs')"
$tmp  = Join-Path $env:TEMP "lbug"

New-Item -ItemType Directory -Force $tmp | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile "$tmp\lbug.zip" `
  "https://github.com/LadybugDB/ladybug/releases/download/$version/liblbug-windows-x86_64.zip"
Expand-Archive "$tmp\lbug.zip" -DestinationPath $tmp -Force

Copy-Item "$tmp\lbug_shared.dll"      $pkg -Force
Copy-Item "$dlls\libcrypto-3.dll" (Join-Path $pkg "libcrypto-3-x64.dll") -Force
Copy-Item "$dlls\libssl-3.dll"    (Join-Path $pkg "libssl-3-x64.dll")    -Force
```

Verify:

```powershell
python -c "import ladybug as lb; c = lb.Connection(lb.Database('')); c.execute('CREATE NODE TABLE T(id STRING PRIMARY KEY)'); print('engine OK')"
```

The download is ~8MB zipped, ~19MB on disk. It lands in `site-packages`, so it
does not survive recreating the venv - redo it after a fresh environment, and note
that upgrading the `ladybug` pin means re-downloading the matching release.

macOS and Linux have the same split (`liblbug-*.tar.gz` assets on the same
release); this has only been walked through on Windows.
