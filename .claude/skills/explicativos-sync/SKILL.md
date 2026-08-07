---
name: explicativos-sync
description: Update the matching file in docs/explicativos/ right after editing Neo4j graph store internals, the Playwright scraper's discovery/click/fill/submit logic, the api_server/rest_scraper modules, or core kernel files (Engine/registries/config/CLI/interfaces). Also use when the user explicitly asks to "actualizar los docs explicativos" or "documentar esto". Do NOT use for changes to generated output (docs/*_prd_*.md, research_logs/, progress_logs/, graph_logs/) or for wiki/-shaped durable lessons - see wiki-update for those.
---

# Sincronizar `docs/explicativos/`

`docs/explicativos/README.md` tiene la tabla que mapea cada doc a los archivos de código que
describe. Antes de nada, leé esa tabla para confirmar qué doc(s) corresponde tocar - no asumas.

## Cuándo dispara

Inmediatamente después de editar cualquiera de estos archivos, en el mismo cambio (no como un
paso separado para "después"):

| Si editaste... | Actualizá... |
|---|---|
| `src/storage/neo4j_graph_store.py`, `src/storage/memory_graph_store.py`, la clase `GraphStore` en `src/core/interfaces.py`, o `_clean_url` en `src/generators/prd_generator.py` | `docs/explicativos/neo4j.md` |
| `src/scrapers/playwright_scraper.py` | `docs/explicativos/playwright.md` |
| `src/api_server/*`, `src/scrapers/rest_scraper.py` | `docs/explicativos/modulo3-api-server-y-rest-scraper.md` |
| `src/core/engine.py`, `src/core/registry.py`, `src/core/config.py`, `src/cli.py`, `src/core/wizard.py`, la forma general del loop en `src/generators/prd_generator.py` (no un detalle interno puntual) | `docs/explicativos/arquitectura.md` |

## Proceso

1. **Releé la sección concreta del doc que tu cambio afecta** antes de tocarla - necesitás saber
   qué dice hoy para no duplicar contenido ni dejar una frase vieja contradiciendo la nueva.
2. **Editá esa sección in place**, en español, con el mismo nivel de detalle y estilo que el resto
   del archivo (tablas para datos estructurados como propiedades/rutas/campos; prosa para el
   "por qué"). No reescribas el documento entero por un cambio puntual.
3. Si agregaste un archivo/módulo nuevo que no encaja en ningún doc existente, considerá si merece
   una fila nueva en la tabla de `docs/explicativos/README.md` en vez de forzarlo dentro de un doc
   que no es su lugar natural - mismo criterio que usa la skill `wiki-update` para decidir "nuevo
   archivo vs. sección existente".
4. Si el cambio de código invalida algo que estos docs asumían como cierto (por ejemplo, si se
   arregla el problema de identidad de URL descripto en `neo4j.md`'s "Problema conocido", o se
   agrega soporte de `frame_url` a `RestScraper`), **reemplazá esa sección**, no la dejes al lado
   de la corrección como si ambas siguieran siendo verdad.

## Qué NO hacer

- No toques estos docs por cambios en archivos generados (`docs/*_prd_*.md`, `research_logs/`,
  `progress_logs/`, `graph_logs/`) - esos son salida de una corrida, no código.
- No dupliques acá una lección de dominio general (eso es `wiki/`, ver la skill `wiki-update`) -
  estos documentos son "cómo funciona esto ahora mismo en este código", no principios reusables
  en otro proyecto.
- No actualices el doc entero "por las dudas" cuando el cambio real es acotado - un diff grande
  en un doc por un cambio chico en código dificulta ver qué cambió realmente la próxima vez.

## Después de actualizar

Decile al usuario qué archivo(s) de `docs/explicativos/` se actualizaron y, en una línea cada
uno, qué cambió - no alcanza con decir "actualicé los docs".
