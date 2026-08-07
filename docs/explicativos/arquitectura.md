# Arquitectura de Pragma, explicada

> Ver también: [`ARCHITECTURE.md`](../../ARCHITECTURE.md) (versión en inglés, más técnica y
> pegada al código). Este documento es el mismo territorio, en español y con más contexto para
> alguien que no vio el proyecto antes.

## Qué es el proyecto

Pragma es una herramienta de **arqueología de aplicaciones web**: le das una URL y un agente
autónomo (un LLM) navega el sitio con un browser real, va descubriendo su estructura (rutas,
componentes interactivos, formularios) y al final genera un **PRD/Blueprint en Markdown** que
documenta cómo está armado el frontend — como ingeniería inversa de una webapp de la que no
tenés el código fuente.

El motor sigue un modelo de 4 fases, el **"Ralph-Loop"** (Plan-Execute-Iterate):

1. **Discovery** — navega a la URL raíz, saca una foto inicial (layout + componentes).
2. **Planning** — el agente arma una estrategia de investigación.
3. **Execution** — itera: lee el progreso persistido, decide una acción (`navigate`, `click`,
   `fill`, `submit`, `finish`, o `help` si está perdido), la ejecuta, registra qué encontró y qué
   arista de navegación usó.
4. **Synthesis** — con todo lo investigado, genera el PRD final.

## El micro-kernel: quién hace qué

El corazón del diseño es que [`src/core/engine.py`](../../src/core/engine.py) (`Engine`) es un
**kernel tonto**: no sabe nada de Playwright, de un proveedor de LLM en particular, ni de los
detalles del loop. Solo resuelve "plugins por nombre" desde cuatro registries
([`src/core/registry.py`](../../src/core/registry.py)):

| Registry | Rol | Implementaciones hoy |
|---|---|---|
| `SCRAPER_REGISTRY` | "Las manos" — interactúa con el sitio | `playwright`, `rest` |
| `AGENT_REGISTRY` | "El cerebro" — el LLM | `gemini`, `openai`, `local`, `mock` |
| `GENERATOR_REGISTRY` | La estrategia de orquestación (el loop) | `simple` (el Ralph-Loop) |
| `GRAPH_STORE_REGISTRY` | Dónde se persiste el grafo de crawl | `memory`, `neo4j` |

Cada plugin se auto-registra con un decorador (ej. `@AGENT_REGISTRY.register("gemini")`), y
[`src/core/bootstrap.py`](../../src/core/bootstrap.py) importa todos los módulos una vez para que
esos registros corran antes de que el CLI resuelva nombres desde la config. Agregar un proveedor
nuevo es: un archivo nuevo con su propia clase + `Config.from_env()`, y una línea de import en
`bootstrap.py` — nada más cambia.

Los contratos compartidos viven en [`src/core/interfaces.py`](../../src/core/interfaces.py):

- **`PageState`** — lo que cualquier `Scraper` devuelve tras navegar/clickear/llenar: url, title,
  metadata, `components` (la lista de elementos interactivos), `links`, y `description` (un
  resumen corto de qué trata la página).
- **`AgentAction`** — la decisión estructurada del agente (`kind`: `navigate`/`click`/`fill`/
  `submit`/`finish`/`help`/`unknown`, más `ref`/`url`/`value` según corresponda). Reemplaza al
  viejo formato de texto plano `GOTO`/`CLICK`/`FINISH` (que sigue soportado como fallback vía
  `parse_agent_action()`, para modelos que no hacen tool-calling nativo).
- **`GraphStore`** — la interfaz de persistencia del grafo de crawl. Ver [`neo4j.md`](neo4j.md)
  para el detalle completo de qué guarda.

## Cómo decide el agente qué hacer: `TOOL_SPECS`

En vez de pedirle al modelo texto libre, `TOOL_SPECS` (en `interfaces.py`) define un menú cerrado
de verbos, cada uno con una descripción de una línea (los modelos chicos/locales pagan cada token
de esto en cada turno, así que se mantiene mínimo a propósito):

| Verbo | Qué hace |
|---|---|
| `navigate(url)` | Ir a una de las rutas "Pending" mostradas |
| `click(ref)` | Clickear el elemento número `ref` de la lista mostrada |
| `fill(ref, value)` | Escribir texto en un input/textarea numerado |
| `submit(ref)` | Apretar Enter sobre un elemento (después de un `fill`) |
| `finish` | Concluir la investigación |
| `help(topic)` | Pedir guía sobre un tema puntual cuando el modelo no sabe cómo seguir |

`Agent.act()` es quien produce un `AgentAction` a partir de la respuesta cruda del modelo,
soportando tanto tool-calling nativo (formato tipo OpenAI) como el fallback de texto — así
`SimplePRDGenerator` nunca necesita saber cuál de los dos pasó.

## Qué mecanismos evitan que el agente se pierda

Esto es información que en su momento no existía y ahora sí — vale la pena tenerla documentada
acá porque cambia bastante cómo se comporta un run real:

- **`_skip_repeated_target`**: si la última acción "en el lugar" (click/fill/submit, sin cambiar
  de página) se repite exactamente en la siguiente iteración, se bloquea — evita quedar
  clickeando el mismo trigger que no lleva a nada nuevo.
- **`_track_oscillation`**: si en las últimas 6 acciones "en el lugar" un mismo target aparece 3+
  veces, se emite una advertencia fuerte al log — típicamente señala un elemento real que el
  discovery no está encontrando, más que un problema del modelo.
- **`_reject_premature_finish`**: no deja terminar el run mientras existan componentes ya
  mostrados y nunca interactuados (`interacted: false` en el grafo), en cualquier página del
  sitio, no solo en la actual.
- **`_apply_diminishing_returns` / `max_stalled_finish_attempts`**: si el conteo de componentes
  sin explorar de una página no baja después de varios chequeos, esa página se "da por perdida"
  (`_given_up_pages`) y deja de bloquear el `finish` — pensado para componentes cuyo selector
  cambia en cada render (ej. un stepper de cantidad) o un submit de login que nunca va a
  resolverse.
- **`max_passes`** (= `max_iterations * 3`): techo duro independiente, para que un modelo que
  solo pide `help` una y otra vez no corra indefinidamente sin gastar su presupuesto real de
  acciones.

Estos mecanismos ya resuelven los casos de "loop de selector de idioma" y "página A→B→A
incompleta" que se discutieron en análisis previos — ver el historial de esta conversación para
el detalle de qué se descartó y por qué.

## Recorrido y contexto: fases 0-3 (navegar profundo, sin olvidos, sin loop)

Cuatro mecanismos agregados en una sesión de trabajo dedicada a "que capte toda la página sin
quedar en loop, con el mayor contexto posible":

- **Fase 0 — Contexto del sitio** (`_establish_site_context`/`_site_context_line`): al arrancar,
  `Scraper.extract_context()` lee la página raíz a fondo (todos los h1/h2/h3 + varios párrafos, no
  solo el primero) y ese texto queda fijo como "Site purpose" en **todas** las iteraciones del run
  — distinto del `Page context` por página, que sigue siendo corto y cambia página a página. Sin
  llamada extra al LLM (usa el texto tal cual lo extrae el scraper) — ver el docstring del método
  para por qué se descartó a propósito sumar una síntesis vía modelo.
- **Fase 1 — Identidad de URL** (`_clean_url`/`_normalize_dynamic_segments`/`_normalize_query`):
  ver [`neo4j.md`](neo4j.md#identidad-de-url-con-tokens-dinámicos-con-arreglo-opt-in-disponible) —
  colapsa tokens dinámicos incrustados en el path y aplica una política de query strings, ambos
  opt-in por sitio vía `pragma.yaml`.
- **Fase 2 — Esqueleto antes que profundidad** (`_seed_from_sitemap`/`_order_pending`): semilla
  best-effort desde `sitemap.xml` (sin costo de iteraciones), y durante los primeros
  `skeleton_iterations` turnos reales las rutas Pending de secciones todavía no visitadas se
  muestran primero; después, se ordenan por `GraphStore.get_incoming_link_counts` (cuántas páginas
  distintas enlazan a cada una). Puramente de reordenamiento — nunca filtra ni fuerza la elección
  del modelo, mismo criterio que ya usa `_select_dna_components` para los componentes.
- **Fase 3 — Selectores sin duplicar variantes** (`record_component_options`'
  `excluded_from_debt`): las opciones reveladas al abrir un desplegable/combobox ya no exigen ser
  clickeadas una por una para permitir `finish` — alcanza con haber interactuado con el disparador
  que las reveló. Siguen existiendo como sus propios `Component` (auditables, listables), solo
  dejan de contar como deuda individual.

## Modo seguro (safe mode)

Pedido original en [`feedback.md`](../../feedback.md): "que no haga mutaciones, que no cambie el
estado". `SimplePRDGenerator._is_mutating_action`/`_block_mutation` interceptan cada `click`/
`submit` (nunca `fill` — escribir texto no envía nada por sí solo) antes de ejecutarlo:
`component_classifier.classify_mutation_risk` marca el componente si (a) su formulario contenedor
manda por `POST` (`PlaywrightScraper` expone el `form_method` real, calculado por el propio
browser — `"get"` es el default del spec HTML si no se especifica) o (b) su texto matchea un verbo
de negocio curado (comprar/eliminar/confirmar/buy/delete/...). Deliberadamente **no** incluye
verbos genéricos como "enviar"/"submit" — bloquearían casi cualquier formulario de contacto
inofensivo.

Una acción bloqueada nunca llega al scraper — se registra como `Component` con
`excluded_from_debt=True` (mismo mecanismo de la Fase 3) y se agrega a
`self._mutation_boundaries`, que termina en una sección `## Safe Mode: Detected Mutation
Boundaries` del PRD final — es parte del entregable, no solo un log interno. `safe_mode: true` es
el default (`--unsafe` en el CLI, o `safe_mode: false` en `pragma.yaml`, para desactivarlo y volver
al comportamiento de ejecutar todo, como antes de esta función).

## Configuración en capas

[`src/core/config.py`](../../src/core/config.py) (`PragmaConfig`) mezcla, en orden creciente de
prioridad: defaults incorporados → variables de entorno → `pragma.yaml` → flags explícitos de
CLI. Incluye, entre otros: `scraper`, `agent`, `generator`, `graph_store`, `max_iterations`,
`batch_size`, `wait_seconds`, y `fresh` (si `true`, por defecto, purga los datos previos de ese
sitio en Neo4j antes de arrancar — ver [`neo4j.md`](neo4j.md#fresh-y-persistencia-entre-corridas)).

## El CLI

[`src/cli.py`](../../src/cli.py) tiene tres modos:

- `python3 src/cli.py config` → wizard interactivo (`src/core/wizard.py`) que guarda config no
  secreta en `pragma.yaml` y secretos en `.env`.
- `python3 src/cli.py <url>` (o con flags) → corre un análisis directo.
- `python3 src/cli.py` sin argumentos, en una terminal real → lanza una app de menú interactivo
  (`src/core/app.py`).

## Los tres "módulos" del sistema completo

Pensar el sistema como tres piezas ayuda a ubicar dónde vive cada cosa:

- **Módulo 1**: el servidor del modelo LLM (remoto, vía Tailscale en el setup actual —
  configurable a cualquier endpoint compatible con la API de OpenAI).
- **Módulo 2**: este orquestador (`SimplePRDGenerator` + `Engine`) — todo lo descripto arriba.
- **Módulo 3**: el servidor REST local (`src/api_server/`) — ver
  [`modulo3-api-server-y-rest-scraper.md`](modulo3-api-server-y-rest-scraper.md) para el detalle.

## Mapa de carpetas

| Carpeta | Rol |
|---|---|
| `src/core/` | El kernel: `Engine`, registries, interfaces (`PageState`, `AgentAction`, `GraphStore`), config en capas |
| `src/scrapers/` | `PlaywrightScraper` ("las manos", en proceso) y `RestScraper` (las mismas manos, vía HTTP a Módulo 3) |
| `src/api_server/` | Módulo 3 — servidor REST standalone (ejecución + docs curadas + checklist de componentes) |
| `src/agents/` | Backends LLM (Gemini, OpenAI, local, mock), cada uno con su `Config.from_env()` |
| `src/storage/` | Persistencia del grafo de crawl: memoria o Neo4j |
| `src/generators/` | El Ralph-Loop (`SimplePRDGenerator`) y `component_classifier.py` (clasificación determinista de componentes, sin LLM) |
| `docs/` | PRDs finales generados por corridas reales, más esta carpeta (`explicativos/`) |
| `research_logs/` | Memoria de trabajo *viva* del run actual (se sobreescribe) |
| `progress_logs/` | Trail de auditoría *append-only*, incluye respuestas crudas del modelo aunque sean inválidas |
| `graph_logs/` | El grafo de navegación como JSON |
| `wiki/` | Lecciones durables de dominio, no atadas al estado actual del código |
