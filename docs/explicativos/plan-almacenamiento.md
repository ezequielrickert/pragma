# Plan de trabajo: almacenamiento de datos y documentos de resultado

> **Alcance de este documento**: cubre exclusivamente el área de responsabilidad de
> almacenamiento/persistencia/documentos de salida (`src/storage/`, `src/generators/`,
> `src/crawlers/graph_sink.py`, `src/utils/io.py`, `docs/`, `debug_logs/`) — no el crawling en sí
> (`src/crawlers/mechanical_loop.py`, `src/crawlers/crawl4ai_crawler.py`), que es responsabilidad de
> otra persona del equipo. Donde un cambio de este plan toca un archivo "del crawler" (por ejemplo,
> volver async las llamadas del sink), se marca explícitamente como tal.

Este documento es el resultado de una investigación del estado actual de la capa de storage tras la
migración a `crawl4ai` (ver `ARCHITECTURE.md`), más research externo de prácticas y librerías
aplicables. Se escribe **antes** de tocar código, para que el resto del equipo pueda revisarlo/
discutirlo, y se va a ir actualizando (sección "Bitácora" al final) a medida que cada fase se
implementa — tanto con lo que salió bien como con cualquier cosa que empeore el sistema.

## Estado actual (línea de base)

- **`GraphStore`** (`src/core/interfaces.py`) es el contrato único de persistencia del crawl, con dos
  implementaciones: `InMemoryGraphStore` (`src/storage/memory_graph_store.py`, proceso-local, no
  persiste) y `Neo4jGraphStore` (`src/storage/neo4j_graph_store.py`, persistente vía
  `docker-compose.yml`).
- **Documentos de salida**: `docs/{slug}_prd_{timestamp}.md` (prosa, `GraphPRDSynthesizer`) y
  `docs/{slug}_tree_{timestamp}.md` (árbol determinístico, `component_tree.py`), escritos por
  `src/utils/io.py::write_output` — un `Path.write_text` simple, sin versionado ni índice.
- **Logs de debug**: `debug_logs/{slug}_{timestamp}/` (`src/crawlers/debug_log.py`) — audit trail
  (`debug.md`) + snapshot markdown por página (`pages/*.md`).
- Todo lo anterior está bien documentado a nivel de diseño (`ARCHITECTURE.md`,
  `wiki/graph-based-crawl-tracking.md`), pero `docs/explicativos/neo4j.md` (la referencia en
  español del esquema) está parcialmente desactualizada.

## Hallazgos (evidencia concreta, no solo intuición)

1. **El driver de Neo4j es síncrono dentro de un loop async — bloquea bajo concurrencia.**
   `MechanicalCrawler.crawl_site` (`src/crawlers/mechanical_loop.py:517`) lanza `page_concurrency`
   workers vía `asyncio.create_task`, pero cada `sink.record_*` (`src/crawlers/graph_sink.py`) llama
   directo a `Neo4jGraphStore`, que usa el driver **síncrono** (`GraphDatabase.driver`,
   `session.run()` bloqueante) sin `await` ni `asyncio.to_thread`. El propio proyecto ya aplicó esta
   disciplina para otra llamada lenta (`fill_value_agent.py` usa `asyncio.to_thread` explícitamente,
   documentado en `ARCHITECTURE.md`) pero no acá. Con `page_concurrency > 1`, cada escritura a Neo4j
   serializa el event loop, reduciendo el beneficio de la concurrencia que el crawler ya soporta.
2. **Sin política de retención** — `docs/` y `debug_logs/` crecen sin límite (nombre con timestamp,
   nunca se limpian ni comprimen).
3. **No hay manifiesto/índice de corridas** — no se puede preguntar "¿cuál es la última corrida de
   `site X`?" sin parsear nombres de archivo del filesystem. Bloquea features obvios (diff entre
   corridas, comparar cómo cambió un sitio en el tiempo).
4. **Cypher muy repetido, sin capa de abstracción** — el patrón
   `MERGE (p:Page {...}) ON CREATE SET ... ON MATCH SET ...` se repite casi textual en 6+ métodos de
   `neo4j_graph_store.py`. Cualquier cambio al shape de `Page`/`Component` obliga a tocar N lugares
   de forma consistente.
5. **Testing de Neo4j real es manual y parcial** — `tests/test_neo4j_graph_store_integration.py` se
   salta si no hay una instancia en `localhost:7687` corriendo a mano. Además,
   `docs/explicativos/pendientes-futuras-fases.md` ya señala que campos más nuevos nunca se probaron
   contra Neo4j real, solo contra `InMemoryGraphStore`.
6. **Sin export estructurado** — todo lo que sale de `GraphStore` termina en prosa o árbol ASCII. No
   hay forma de volcar el grafo (páginas, componentes, edges) en un formato que otra herramienta
   pueda consumir.
7. **Los ledgers cargan el sitio entero en memoria de una** — `get_component_ledger`/
   `get_text_content_ledger` (ambos backends) devuelven todo en un solo dict. No es un problema hoy
   (sitios de prueba chicos), pero es un riesgo de escala conocido y sin mitigar.
8. **Sin estrategia de backup/restore documentada para Neo4j** — `docker-compose.yml` usa named
   volumes pero no hay script ni instrucción de backup.
9. **`docs/explicativos/neo4j.md` desactualizado** (ya marcado como tal en el propio doc) — no cubre
   `description`/`title`, `network_requests`, ni el nodo `TextContent`.
10. **Aislamiento de tests roto en `test_graph_store.py`** (encontrado corriendo la suite en
    aislamiento, no en investigación previa): dos tests que llaman `Engine.from_config` fallan si se
    corre solo ese archivo, porque `AGENT_REGISTRY`/`GRAPH_STORE_REGISTRY` solo se pueblan importando
    `src/core/bootstrap`, y solo `src/cli.py` hace ese import — ningún test ni `conftest.py` lo hace.
    Pasa desapercibido corriendo la suite completa (algún otro archivo importa un módulo de agente
    antes, por casualidad de orden de colección), pero es un test suite fragile por diseño. No es
    estrictamente "storage", pero bloquea señal confiable sobre cambios en `Engine`/`GraphStore`, así
    que se corrige como parte de la Fase A.

## Librerías/herramientas evaluadas

| Herramienta | Para qué | Conclusión |
|---|---|---|
| `neo4j.AsyncGraphDatabase` (ya en `requirements.txt`, v5.24) | Resolver el hallazgo #1 | Sin dependencia nueva — es cambio de código. Ver [Async API docs](https://neo4j.com/docs/api/python-driver/current/async_api.html) y [concurrency manual](https://neo4j.com/docs/python-manual/current/concurrency/). |
| `testcontainers[neo4j]` | CI/tests reproducibles sin Neo4j corriendo a mano (#5) | Dependencia nueva de test únicamente. Ver [módulo Neo4j](https://testcontainers-python.readthedocs.io/en/testcontainers-v4.5.0/modules/neo4j/README.html). |
| `neo4j-python-migrations` | Versionar cambios de esquema | Evaluado, **no se adopta por ahora** — el patrón actual `CREATE CONSTRAINT ... IF NOT EXISTS` ya es idempotente y el esquema no cambia con la frecuencia que justificaría la herramienta. Revisar si eso cambia. |
| Neo4j GDS (plugin) | PageRank real en vez de grado de entrada simple | Cruza con el área del crawler (afecta priorización), la lectura del grafo sería storage — **fuera de alcance de este plan**, ya señalado en `feedback.md`/`pendientes-futuras-fases.md`. |
| `mkdocs-material` | Sitio navegable de los PRDs/trees acumulados | Nice-to-have, evaluado en Fase E. |
| JSON estándar (sin librería nueva) | Export estructurado (#6) | Gratis, las estructuras Python ya existen. |
| `neo4j-admin dump/load` | Backup/restore (#8) | Community Edition solo soporta offline (contenedor detenido). Ver [docs oficiales](https://neo4j.com/docs/operations-manual/current/docker/dump-load/). |

## Fases

Cada fase se cierra con commit(s) descriptivos + push a esta rama, para que quede todo separable y
revisable por partes.

### Fase A — Quick wins (bajo riesgo)
1. Manifiesto de corridas por sitio (`docs/{site}/index.json`) — resuelve #3.
2. Retención configurable de `debug_logs/` — resuelve #2.
3. `--export json` en el CLI/Engine — resuelve #6.
4. Fix de aislamiento de tests (`conftest.py` importa `bootstrap`) — resuelve #10.
5. Actualizar `docs/explicativos/neo4j.md` — resuelve #9.

### Fase B — Correctness/performance (riesgo medio, toca `graph_sink.py`/`mechanical_loop.py`)
6. Migrar `Neo4jGraphStore` al driver async — resuelve #1. Es el cambio más invasivo del plan porque
   propaga `await` a través de `GraphStoreSink`/`GraphStoreInteractionTracker` y de cada call site en
   `mechanical_loop.py` (código del crawler) — se coordina/documenta explícitamente por eso.
7. Refactor de los patrones Cypher repetidos a helpers compartidos — resuelve #4 y reduce el riesgo
   del punto anterior.

### Fase C — Calidad/testing
8. `testcontainers[neo4j]` para integration tests reproducibles — resuelve #5 (parcial).
9. Cobertura contra Neo4j real de los campos marcados como pendientes en
   `docs/explicativos/pendientes-futuras-fases.md`.

### Fase D — Operabilidad
10. Script de backup/restore (`neo4j-admin dump`/`load`) + documentación — resuelve #8.

### Fase E — Nice-to-have
11. Mitigación de escala para sitios grandes (#7) — solo si se justifica con evidencia, no
    especulativamente (misma filosofía que ya usa el proyecto: ver `pendientes-futuras-fases.md`).
12. Exploración de `mkdocs-material` para navegar el historial de `docs/`.

## Bitácora de riesgos y aprendizajes

> Se actualiza al cerrar cada fase, con lo que se confirmó, lo que sorprendió, y cualquier cosa que
> haya empeorado el sistema (o el riesgo de que lo haga) — no solo lo que salió bien.

- *(pendiente — se completa a medida que cada fase cierra)*
