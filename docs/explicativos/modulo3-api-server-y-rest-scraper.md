# Módulo 3: el servidor REST (`api_server`) y `RestScraper`

> Código de referencia: [`src/api_server/`](../../src/api_server/) y
> [`src/scrapers/rest_scraper.py`](../../src/scrapers/rest_scraper.py). Ver también la sección
> "Module 3" de [`ARCHITECTURE.md`](../../ARCHITECTURE.md), que es la fuente original de esta
> nomenclatura de "Módulo 1/2/3".

## Por qué existe

Pensando el sistema completo como tres piezas — **Módulo 1**: el servidor del modelo LLM (remoto),
**Módulo 2**: el orquestador (`SimplePRDGenerator`, todo lo de [`arquitectura.md`](arquitectura.md)
y [`playwright.md`](playwright.md)) — este es el **Módulo 3**: un servicio local que separa la
*vida* de la sesión de browser de la vida de una corrida puntual del orquestador. Antes, cada
`python3 src/cli.py <url>` abría y cerraba su propio Chromium. Con el Módulo 3 levantado una sola
vez y dejado corriendo, sucesivas corridas (o herramientas externas) comparten la misma sesión ya
abierta.

## Cómo se arranca

```bash
python -m src.api_server
```

Queda escuchando en `127.0.0.1:8765` por defecto (`PRAGMA_API_HOST`/`PRAGMA_API_PORT` para
cambiarlo). **Importante**: una instancia corriendo no recoge cambios de código — si estás
iterando sobre `src/api_server/` o `playwright_scraper.py`, corré con `PRAGMA_API_RELOAD=1` para
que uvicorn reinicie solo ante cada guardado (no lo dejes así para uso normal: un restart en cada
save tira la sesión de browser viva, justo lo que este diseño busca evitar).

## Las tres rutas

| Prefijo | Archivo | Qué expone |
|---|---|---|
| `/dynamic/*` | `dynamic.py` | Ejecución real contra el browser: `POST navigate/click/fill/submit`, `GET state`. Envuelve 1 a 1 los métodos de una única instancia de `PlaywrightScraper`, viva durante toda la vida del proceso servidor. |
| `/static/*` | `static_docs.py` | `GET /static/topics` (lista), `GET /static/{topic}` — los mismos textos curados a mano que el agente pide vía el verbo `help` (`fill_submit_flow`, `ref_semantics`, `text_field_values`, etc.). Sin embeddings ni búsqueda vectorial: vocabulario cerrado, igual que los verbos de `TOOL_SPECS`. |
| `/components/*` | `components.py` | Solo lectura sobre los nodos `Component` persistidos en Neo4j: `GET /components/state?site=..&page_url=..` (el checklist preciso de una página) y `GET /components/debt?site=..` (páginas con componentes sin interactuar, el mismo "debe" que usa `_reject_premature_finish`). Requiere `graph_store: neo4j` — con `memory` devuelve 503, porque nada persiste entre procesos en ese caso. |

Punto clave de diseño: **el modelo nunca llama a estas rutas directamente** — no tiene acceso de
red. Elige un verbo de `TOOL_SPECS` (`navigate`/`click`/`fill`/`submit`/`help`), y es
`SimplePRDGenerator` (Módulo 2) quien traduce esa elección en la llamada HTTP real contra el
Módulo 3. Por eso cambiar de transporte (este módulo reemplazó una versión anterior basada en MCP)
nunca tocó el contrato de cara al modelo.

## El detalle técnico de `/dynamic/*`: un solo hilo para Playwright

La API sync de Playwright no tolera correr dentro de un hilo con un event loop asíncrono activo —
que es exactamente lo que tienen los hilos de manejo de requests de uvicorn/FastAPI. Por eso
`playwright_runtime.py` no usa el threadpool default de FastAPI (que reparte trabajo entre hilos
intercambiables): arma su propio `ThreadPoolExecutor(max_workers=1)` dedicado, y **cada** llamada
a Playwright, durante toda la vida del proceso, se ejecuta en ese único hilo. `graph_store_runtime.py`
(para `/components/*`) no necesita este cuidado — el driver de Neo4j sí es thread-safe para
sesiones concurrentes.

`SimplePRDGenerator` sigue resolviendo `ref → selector` de su lado (`_dna_index_map`) antes de
llamar a cualquier ruta de `/dynamic/*` — el servidor solo recibe selectores CSS ya resueltos,
nunca números de referencia.

## `RestScraper`: el mismo contrato, otro transporte

[`rest_scraper.py`](../../src/scrapers/rest_scraper.py) implementa la interfaz `Scraper` haciendo
llamadas HTTP síncronas (`requests`) a `/dynamic/*` en vez de manejar Playwright en el mismo
proceso. Mismas firmas, mismo contrato de "una falla real se propaga como excepción" que
`PlaywrightScraper` — así que activar `--scraper rest` en vez de `--scraper playwright` es
transparente para `SimplePRDGenerator`.

`RestConfig.from_env()` es el único lugar que lee `PRAGMA_API_URL` (default
`http://127.0.0.1:8765`) — mismo patrón de encapsulamiento por proveedor que el resto del
proyecto (ver el `Config.from_env()` de cada agente LLM).

`close()` es intencionalmente un no-op: el Módulo 3 no le pertenece a esta corrida del
orquestador, así que terminar una corrida no debe apagar la sesión de browser compartida.

**Gap conocido**: a diferencia de `PlaywrightScraper.click/fill/submit`, `RestScraper` todavía no
acepta `frame_url` — no hay parámetro de targeting de frame en las rutas de `/dynamic/*` todavía.
Un componente dentro de un iframe real falla con un `TypeError` claro (capturado por
`_execute_action`, que saltea esa iteración en vez de romper el run) en vez de actuar sobre el
documento equivocado en silencio. Todo componente fuera de un iframe —la inmensa mayoría— no se ve
afectado.

`DocsClient` (en el mismo archivo) es el cliente para `/static/*`, usado cuando la decisión del
modelo es `help`. A diferencia de una acción de browser fallida, un `help` que no se puede resolver
(servidor caído, topic desconocido) no aborta el run — degrada a "sin guía extra este turno".

## Debug manual, sin pasar por el LLM

```bash
curl http://127.0.0.1:8765/static/topics
curl -X POST http://127.0.0.1:8765/dynamic/navigate -d '{"url": "https://example.com"}'
curl "http://127.0.0.1:8765/components/debt?site=example.com"
```

Útil para aislar si un problema es "el servidor/selector" o "el modelo", sin depender del loop
completo del agente.
