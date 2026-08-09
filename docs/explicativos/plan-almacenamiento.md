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

### Fase B — Correctness/performance (alcance revisado durante la implementación — ver Bitácora)
6. ~~Migrar `Neo4jGraphStore` al driver async~~ — **descartado para esta fase** (ver Bitácora): la
   migración completa obliga a volver `async` código de `mechanical_loop.py` documentado
   explícitamente como sincrónico *a propósito* (`_transition_to_new_state`, `_enqueue`) — un cambio
   de mayor alcance/riesgo del que corresponde asumir unilateralmente sobre código de otra persona
   sin su revisión directa.
6b. **Implementado en su lugar**: cachear localmente `GraphStoreInteractionTracker` (una lectura de
    `GraphStore` por página por instancia de tracker, no una por cada chequeo de componente) —
    ataca el patrón N+1 real que agravaba el hallazgo #1, sin tocar `mechanical_loop.py` en
    absoluto.
7. Refactor de los patrones Cypher repetidos a helpers compartidos — resuelve #4.

### Fase C — Calidad/testing (cerrada, ver Bitácora para el detalle de `testcontainers[neo4j]` vs `testcontainers`)
8. `testcontainers` (paquete base, no el extra `[neo4j]` — ver Bitácora) para integration tests
   reproducibles sin depender de `docker compose up -d neo4j` corrido a mano — resuelve #5.
9. ~~Cobertura contra Neo4j real de los campos marcados como pendientes en
   `pendientes-futuras-fases.md`~~ — no abordado esta fase, ver Bitácora.

### Fase D — Operabilidad
10. Script de backup/restore (`neo4j-admin dump`/`load`) + documentación — resuelve #8.

### Fase E — Nice-to-have
11. Mitigación de escala para sitios grandes (#7) — solo si se justifica con evidencia, no
    especulativamente (misma filosofía que ya usa el proyecto: ver `pendientes-futuras-fases.md`).
12. Exploración de `mkdocs-material` para navegar el historial de `docs/`.

## Bitácora de riesgos y aprendizajes

> Se actualiza al cerrar cada fase, con lo que se confirmó, lo que sorprendió, y cualquier cosa que
> haya empeorado el sistema (o el riesgo de que lo haga) — no solo lo que salió bien.

### Fase A (cerrada)

- **Confirmado en la práctica, no solo en teoría**: `tests/test_graph_store.py` corrido en
  aislamiento (`pytest tests/test_graph_store.py`) efectivamente fallaba 2/16 tests con
  `KeyError: "Unknown agent 'mock'"` antes del fix de `conftest.py` (hallazgo #10) — no era una
  hipótesis, se reprodujo. Con el import de `bootstrap` en `conftest.py`, los mismos 16 tests pasan
  en aislamiento. Riesgo si algo similar vuelve a pasar: cualquier test nuevo que use
  `Engine.from_config`/`*_REGISTRY.create()` sin que otro archivo haya importado antes un módulo de
  agente/store va a fallar igual si se corre solo — el fix es a nivel de sesión de pytest
  (`conftest.py`), así que cualquier test nuevo queda cubierto automáticamente.
- **Decisión consciente**: `record_run_manifest` (`docs/runs.json`) NO tiene locking entre procesos
  — es read-modify-write simple. Documentado explícitamente en el docstring como limitación
  aceptada para el patrón de uso actual (un `Engine` por proceso). Si en algún momento se corren
  crawls en paralelo contra el mismo `out_dir` (ej. un scheduler que dispara varias corridas a la
  vez), este archivo puede perder entradas por una carrera de escritura — no habría corrupción de
  JSON grave (cada escritura es atómica a nivel de `write_text`), pero sí una entrada de las dos
  corridas concurrentes puede pisar a la otra si ambas leen antes de que la otra escriba. Señalado
  acá para no perderlo de vista si el patrón de uso cambia.
- **Nada de esta fase modificó el comportamiento por defecto** — `export_json` y
  `debug_logs_keep_last` son opt-in (`False`/`None`), así que cualquier corrida existente sin tocar
  `pragma.yaml`/flags se comporta exactamente igual que antes, más la escritura (siempre activa,
  pero nueva) de `docs/runs.json`. Ese es el único cambio de comportamiento por defecto de la fase —
  aceptado a propósito porque es puramente aditivo (un archivo nuevo, nunca lee ni depende de nada
  existente) y de bajo costo (un `json.dumps` de unos pocos campos por corrida).
- **Pendiente para una fase futura, no de esta**: no hay `README.md` en `docs/` (la carpeta de
  salida) explicando qué es `runs.json` para alguien que la encuentre sin haber leído este plan —
  candidato para Fase E si se arma el sitio `mkdocs-material`, o un README chico suelto antes si no
  se llega a esa fase. *(Actualización: se agregó igual durante esta misma fase — ver
  [`docs/README.md`](../README.md) — resultó barato y de bajo riesgo, no ameritaba esperar.)*

### Fase B (cerrada — alcance recortado a propósito, ver por qué)

- **Hallazgo revisado en el momento de implementar, no antes**: al leer `mechanical_loop.py` a fondo
  para planear el cambio, encontré que `_transition_to_new_state` es **explícitamente** un método
  sincrónico por diseño (su propio docstring: *"Pure bookkeeping, no crawler I/O ... kept as a plain
  method, not async, for exactly that reason"*), y llama a `self.sink.record_navigation_edge`/
  `record_page_finished`/`record_page_arrival`/`record_inventory`/`record_text_content` y a
  `self.tracker.is_interacted`. `_enqueue` (también sincrónico) llama a `self.tracker.is_visited`.
  Migrar `GraphStoreSink`/`GraphStoreInteractionTracker` a `async def` — el plan original de esta
  fase — obliga en cascada a volver `async` estos dos métodos también, contradiciendo una decisión
  de diseño explícita y documentada del propio crawler, no solo agregando `await` de forma mecánica.
  Esto cambia la evaluación de riesgo: no es un refactor de bajo riesgo confinado a `src/storage/`,
  es un cambio real al modelo de control del crawler.
- **Decisión**: no forzar ese cambio unilateralmente sobre código ajeno sin que la otra persona lo
  revise — en su lugar, buscar el mejor arreglo posible que no cruce esa frontera. Encontrado uno
  mejor de lo esperado: `GraphStore.get_component_states`'s propio docstring en
  `src/core/interfaces.py` ya documentaba el contrato como *"one query per page visit, not one per
  component"*, pero `GraphStoreInteractionTracker.is_interacted` no lo cumplía — llamaba a
  `get_component_states` fresco en cada chequeo, y `_visit_page`'s frontier loop llama a
  `is_interacted` una vez por componente considerado en cada pasada. Para una página de N
  componentes, eso son N round-trips reales a `GraphStore` (a Neo4j por red, si `graph_store: neo4j`)
  para responder repetidamente la misma pregunta sobre una página que apenas cambió. Confirmado con
  tests dedicados (`tests/test_graph_sink_tracker_cache.py`, un `GraphStore` "spy" que cuenta
  llamadas reales) que antes del fix esto era exactamente N llamadas, no 1.
- **Lo que se implementó**: cachear localmente por instancia de `GraphStoreInteractionTracker` (una
  lectura real de `GraphStore` por página, no por componente) — mismo patrón para `is_visited`.
  `mark_interacted`/`mark_visited` (antes no-ops puros) ahora actualizan esa caché local en el mismo
  punto donde el escritor real (`GraphStoreSink`) hace el write real, así que la caché nunca queda
  desincronizada de lo que esta misma corrida escribió. Cero cambios de firma o de comportamiento
  observable desde `mechanical_loop.py` — sigue siendo la misma interfaz sincrónica, mismos call
  sites, sin tocar ese archivo en absoluto.
- **Qué NO resuelve esto**: el hallazgo #1 original (bloqueo del event loop bajo `page_concurrency >
  1` durante las escrituras reales - `record_interaction`, `record_inventory`, etc.) sigue existiendo
  tal cual - esta caché reduce drásticamente la *frecuencia* de las llamadas bloqueantes de lectura
  (que dominaban en cantidad sobre las de escritura), pero no elimina el bloqueo de las escrituras.
  **Queda como trabajo futuro, explícitamente NO recomendado para hacer unilateralmente**: la
  migración completa al driver async de Neo4j, coordinada con quien mantiene `mechanical_loop.py`,
  dado que toca invariantes de control de flujo que esa persona diseñó y documentó a propósito.
- **Riesgo real evaluado y aceptado**: la caché asume que ningún otro proceso/tracker escribe al
  mismo `site` concurrentemente durante esta corrida - no es un riesgo nuevo (la arquitectura ya
  asume un único escritor por sitio por corrida vía `PragmaConfig.fresh`/`clear_site`), pero vale
  dejarlo explícito acá por si ese supuesto cambia en el futuro (ver hallazgo sobre
  `record_run_manifest` en la bitácora de Fase A - mismo tipo de supuesto).
- **Verificación**: `tests/test_graph_sink.py` + `tests/test_mechanical_loop.py` completos (33 tests,
  incluyendo los casos más sensibles a este cambio - re-interacción entre instancias de
  `MechanicalCrawler`, drenado de páginas con más componentes que el budget, abandono de páginas que
  nunca convergen) en verde después del cambio, más 7 tests nuevos dedicados a la caché en sí.
- **Punto 7 (refactor de Cypher repetido) sí se hizo completo esta fase** - cero riesgo para el
  crawler porque toca únicamente `src/storage/neo4j_graph_store.py`. `_page_ensure_clause()`
  reemplaza 9 copias manuales del mismo bloque `MERGE (x:Page ...) ON CREATE SET ...` (7 métodos, 2
  de ellos con dos endpoints cada uno) por una sola función que genera el fragmento; `_COMPONENT_BLANK_STUB`
  unifica 3 copias casi idénticas del stub de auto-creación de `Component`, corrigiendo en el camino
  una divergencia real entre ellas (`record_component_options` no seteaba `c.options = ''` en su
  copia, las otras dos sí - inofensivo porque un `SET` incondicional lo pisa después de todas formas,
  pero era exactamente el tipo de drift silencioso que este refactor existe para prevenir a futuro).
- **Limitación honesta de la verificación**: no pude correr esto contra una instancia real de Neo4j
  en este entorno — Docker está instalado (`docker --version` funciona) pero el daemon de Docker
  Desktop no está corriendo (`docker compose up -d neo4j` falla al conectar al pipe), y no intenté
  forzar el arranque de una app de escritorio desde acá. Mitigado con: comparación manual del texto
  Cypher generado contra el original (idéntico, campo por campo), tests unitarios dedicados
  (`tests/test_neo4j_cypher_helpers.py`) que verifican el contenido exacto y el balanceo de llaves
  de cada fragmento generado sin necesitar conexión, y que `tests/test_neo4j_graph_store_integration.py`
  sigue teniendo el mismo comportamiento de auto-skip que antes (no se tocó su lógica). **Pendiente
  real**: correr `tests/test_neo4j_graph_store_integration.py` contra una instancia real antes de
  mergear a `main`, o que alguien con Docker Desktop corriendo lo confirme en la revisión de la PR.

### Fase C (cerrada)

- **Hallazgo real, no anticipado en el plan original**: `pip install "testcontainers[neo4j]"` (lo que
  el plan original proponía) fuerza un upgrade silencioso de `neo4j==5.24.0` (el pin de
  `requirements.txt`, el mismo driver que usa `Neo4jGraphStore` en producción) a `neo4j>=6` — el
  extra `[neo4j]` de `testcontainers` lo declara como dependencia dura. Confirmado instalándolo en
  este entorno: `pip` efectivamente desinstaló 5.24.0 e instaló 6.2.0 sin pedir confirmación. Subir
  la versión mayor del driver de producción como efecto secundario de instalar una herramienta *de
  test* es exactamente el tipo de regresión silenciosa que este plan existe para prevenir, no para
  causar.
- **Decisión**: usar el paquete base `testcontainers` (sin el extra `[neo4j]`) y su
  `DockerContainer` genérico para levantar el contenedor (mismo `neo4j:5.24-community` que
  `docker-compose.yml`), pero seguir haciendo todas las queries reales con el driver pineado del
  propio proyecto (`Neo4jGraphStore`) — cero conflicto de versión, cero cambio a `requirements.txt`
  de producción. El costo: un poco más de código manual (esperar el log `"Bolt enabled on"` en vez
  de usar el `Neo4jContainer` ya armado que trae el extra) — aceptado a cambio de no tocar una
  dependencia de producción sin necesidad real. Se documentó en `requirements-dev.txt` (nuevo).
- **Bug real encontrado y arreglado en el camino** (no hipotético — lo disparó este mismo entorno):
  la primera versión de la fixture envolvía `container.start()` en un `try/except` pero *no* la
  construcción de `DockerContainer(...)` en sí — resultó que `DockerContainer.__init__` ya habla con
  el cliente de Docker de forma eager, así que con el daemon de Docker Desktop no corriendo (el mismo
  estado real de este entorno, confirmado en la Fase B), la excepción se disparaba *fuera* del
  `try/except` y rompía la fixture entera con un ERROR en vez de degradar a skip. Corregido moviendo
  la construcción adentro del mismo bloque. Verificado en este mismo entorno: antes del fix, los 14
  tests terminaban en `ERROR`; después, los 14 hacen `skip` limpio - exactamente el comportamiento
  esperado en un entorno sin Docker corriendo, que es justo lo que este entorno es.
- **Lo que NO se hizo esta fase** (punto 9 del plan original): no se agregó cobertura nueva contra
  Neo4j real para los campos marcados como pendientes en `pendientes-futuras-fases.md`
  (`get_incoming_link_counts`, `excluded_from_debt`) porque esos métodos **ya no existen** en la
  interfaz `GraphStore` vigente (`src/core/interfaces.py`) — eran parte de la arquitectura anterior a
  la migración a `crawl4ai`, superada según el propio aviso al pie de `pendientes-futuras-fases.md`.
  Ese punto del plan quedó obsoleto antes de poder ejecutarse; no hay nada real que cubrir ahí hoy.
- **Verificación real de tier 2 (contenedor efectivamente levantado) sigue sin poder confirmarse en
  este entorno** — mismo motivo que en la Fase B (Docker Desktop no llega a levantar el daemon acá).
  Lo que sí se validó en este entorno, de verdad: el fallback a tier 3 (sin Docker disponible) y la
  ruta tier 1 (instancia ya alcanzable) - ambas ejercitadas por los 14 tests existentes, que pasan de
  `ERROR` a `skip` correctamente. **Pendiente real, igual que en Fase B**: confirmar tier 2 con
  Docker Desktop corriendo antes de mergear, o en la revisión de la PR.
