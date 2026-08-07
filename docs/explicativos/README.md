# Documentos explicativos de Pragma

Esta carpeta explica, en español y con más detalle pedagógico, **cómo funciona cada pieza
concreta** del proyecto hoy: Neo4j, Playwright, el servidor REST (Módulo 3), y la arquitectura
general. Son documentos vivos, no una foto única — la idea es que reflejen siempre el estado
real del código, no una versión pasada de él.

No reemplazan a [`ARCHITECTURE.md`](../../ARCHITECTURE.md) (en inglés, más terso, pensado como
referencia rápida junto al código) ni a [`wiki/`](../../wiki/README.md) (lecciones durables que
aplican más allá de este proyecto puntual). Esta carpeta es la capa intermedia: explicaciones
completas, en español, organizadas por subsistema, para alguien que necesita entender una pieza
a fondo sin tener que leer el código fuente primero.

## Índice y qué código cubre cada uno

| Documento | Explica | Se queda desactualizado si cambia... |
|---|---|---|
| [`arquitectura.md`](arquitectura.md) | El proyecto en general: qué es, el micro-kernel, las registries, la config en capas, el CLI, y el flujo completo del Ralph-Loop (Módulos 1/2/3). | `src/core/*`, `src/cli.py`, `src/generators/prd_generator.py` (el loop en general, no cada detalle interno) |
| [`neo4j.md`](neo4j.md) | Qué nodos y relaciones existen en el grafo, de dónde salen los `<id>`/`<elementId>`, cómo se evita duplicar páginas/componentes, y el problema conocido de identidad de URL. | `src/storage/neo4j_graph_store.py`, `src/storage/memory_graph_store.py`, `src/core/interfaces.py` (la clase `GraphStore`), la función `_clean_url` en `prd_generator.py` |
| [`playwright.md`](playwright.md) | Cómo el scraper descubre componentes (capas semántica/pointer, Shadow DOM, iframes), cómo ejecuta click/fill/submit, y qué información saca de cada página. | `src/scrapers/playwright_scraper.py` |
| [`modulo3-api-server-y-rest-scraper.md`](modulo3-api-server-y-rest-scraper.md) | El servidor REST standalone (`src/api_server/`) y `RestScraper`, la alternativa a Playwright-en-proceso. | `src/api_server/*`, `src/scrapers/rest_scraper.py` |

## Política: mantenerlos al día

**Si tocás alguno de los archivos de la columna de la derecha, actualizá el documento
correspondiente en el mismo cambio** — no como un paso aparte para "después". Un doc desactualizado
es peor que no tener doc, porque alguien va a confiar en él.

Esto está reforzado como una skill de Claude Code: [`.claude/skills/explicativos-sync/SKILL.md`](../../.claude/skills/explicativos-sync/SKILL.md)
dispara automáticamente cuando se edita uno de los archivos de la tabla de arriba, y guía a
actualizar la sección concreta que cambió (no reescribir el doc entero). Mismo patrón que ya usan
[`wiki-update`](../../.claude/skills/wiki-update/SKILL.md) / [`wiki-context`](../../.claude/skills/wiki-context/SKILL.md)
para `wiki/`, aplicado acá a "cómo funciona ahora mismo" en vez de "qué lección general aprendimos".

Última vez que se revisó todo el set contra el código real: commit `e15973f` (rama `scraper`,
"readme guide").
