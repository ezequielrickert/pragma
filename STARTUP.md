# Startup

Setup once per environment:

```bash
pip install -r requirements.txt
python -m playwright install
```

On Windows, run this to install the native `ladybug` library:

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

---

## Run everything automatically (Crawl + Docs + Interactive Server + SPA)

You can run the entire pipeline with a single command. It will execute the crawl, generate the documentation, spawn the interactive Flask backend and the Vite dev server in new windows, and open your browser automatically.

```powershell
# Run interactively (it will prompt for the URL):
.\run_all.ps1

# Or specify the URL directly:
.\run_all.ps1 -Url "https://www.empanad.app"
```

Once launched, the dashboard will open automatically at:
**`http://localhost:5173`**

---

## Running phases and servers separately

If you prefer to inspect state between phases, customize configurations, or run servers manually, you can invoke the individual commands:

Every command refers to a site by its **slug/host** (e.g. `example.com` or `www.empanad.app`).

### 1. The Crawl
```bash
python cli.py crawl https://example.com
```
*Chains the static -> cluster -> dynamic phases and commits the graph state to the database.*

### 2. Document Generation
```bash
python cli.py docs example.com
```
*Generates the prose documents, OpenAPI specifications, tree, and `export.json` under `data/output/example.com/`.*

### 3. Interactive Flask Backend
```bash
python cli.py interactive example.com
```
*Serves the backend REST API on `http://127.0.0.1:5050`.*

### 4. Vite Frontend Dev Server
In a separate terminal:
```bash
cd tools/graph-explorer
npm run dev
```
*Launches Vite on `http://localhost:5173` (with proxies redirected to Flask).*
