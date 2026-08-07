# Residuos y trabajo futuro (fases 0-3)

Este documento junta todo lo que quedó **deliberadamente afuera de alcance** al implementar las
cuatro fases de "navegar profundo, sin olvidos, sin loop" (ver
[`arquitectura.md`](arquitectura.md#recorrido-y-contexto-fases-0-3-navegar-profundo-sin-olvidos-sin-loop)),
para que se pueda retomar en una fase futura sin tener que releer todo el historial de commits. No
es un changelog — cada punto explica **qué falta y por qué se dejó afuera**, no solo "está
pendiente".

## Fase 3 — Selectores/desplegables

- **Steppers y grupos de radio/checkbox no reciben el mismo tratamiento** que las opciones
  reveladas de un combobox. Hoy `record_component_options` soporta `excluded_from_debt`, pero
  `_record_single_snapshot_groupings` (la función que arma `stepper_decrement`/`stepper_increment`/
  `stepper_value` y `choice_group_member`) no lo usa — cada botón de un stepper y cada radio de un
  grupo sigue exigiendo su propia interacción individual para no bloquear `finish`.
  - *Por qué se dejó afuera*: un stepper o un grupo de radio suele tener 2-5 miembros (no docenas,
    a diferencia de un desplegable de sabores), así que el costo real es mucho menor. Extender el
    mismo criterio ahí es sencillo (misma mecánica, otro `kind`), pero cambia el comportamiento de
    tests ya existentes que asumen que cada miembro cuenta — se prefirió no tocar ese
    comportamiento sin una razón concreta que lo pida.

## Fase 0 — Contexto del sitio

- **`RestScraper` no implementa `extract_context`** — Módulo 3 (`src/api_server/`) no tiene una
  ruta `/dynamic/context` todavía. Con `--scraper rest`, `_establish_site_context` cae al fallback
  (`PageState.description`, mucho más corto) en vez de la extracción profunda.
  - *Para retomarlo*: agregar `POST /dynamic/context` (o `GET`) en `src/api_server/dynamic.py` que
    llame a `PlaywrightScraper.extract_context()` del lado del servidor, y el método equivalente en
    `RestScraper`.
- **No hay validación determinística de que un valor de `fill` sea coherente con el `site_context`**
  — la Fase 0 solo le muestra el contexto al modelo y le pide (vía el help topic
  `text_field_values`) que lo use; no hay ningún chequeo de código que rechace un valor
  evidentemente incoherente (ej. "lapicera" en un campo de sabor). Sigue dependiendo del modelo.
  - *Por qué se dejó afuera*: validar "coherencia semántica" de forma determinística sin LLM no es
    trivial (necesitaría una lista de vocabulario por categoría de negocio, algo que no se puede
    generalizar a cualquier sitio sin heurísticas frágiles). Quedaría para una fase que evalúe
    específicamente esto, probablemente con una llamada a un modelo dedicada a validar (no a
    decidir la acción), fuera del flujo de decisión principal para no repetir el problema de
    "consumir slots del script" que se documentó en el commit de la Fase 0.

## Fase 1 — Identidad de URL

- **La normalización de segmentos dinámicos no se aplica dentro de una ruta de hash-SPA
  conservada** (`#/products/123` — ver el propio docstring de `_clean_url`, que ya documentaba esto
  como gap desde antes de esta sesión). Un sitio hash-routeado con tokens dinámicos en su propia
  ruta de hash seguiría sufriendo el problema original.
- **Es puramente opt-in, nunca automático** — un sitio nuevo con URLs tokenizadas sigue
  produciendo el problema tal cual hasta que alguien note el patrón en Neo4j Browser y configure
  `dynamic_url_segments` a mano. Se decidió así a propósito (ver el commit de la Fase 1: una
  heurística automática de "esto parece un token" arriesga fusionar por error un ID de producto
  real). Una fase futura podría agregar una *sugerencia* automática — ej. un script que analice el
  grafo ya construido y proponga patrones candidatos para que un humano los confirme — sin activar
  nada solo.
- **`_template_sample_urls` (el mapeo de clave-con-plantilla → primera URL real vista) vive en
  memoria del proceso, no en `GraphStore`.** Con `graph_store: neo4j` y `--no-fresh` (crawl
  multi-sesión), si el proceso se reinicia, ese mapeo se pierde — una ruta Pending con plantilla
  que sobrevivió de una sesión anterior no tendría URL de muestra en la sesión nueva, y
  `_resolve_goto_url` caería al intento de navegar al string literal con `{id}` (falla de forma
  controlada, se saltea esa iteración, pero no llega a visitarla).
  - *Para retomarlo*: persistir el sample en el propio nodo `Page` (ej. una propiedad
    `sample_url`), seteada la primera vez que `upsert_page` ve una URL cuya clave contiene `{id}`.

## Fase 2 — Esqueleto y prioridad

- **La señal de importancia es solo grado de entrada simple** (cuántas páginas distintas enlazan a
  una URL), no una centralidad real como PageRank. Se evaluó Neo4j Graph Data Science (GDS) en el
  análisis previo a esta implementación y se decidió no era necesario para esta primera versión.
  - *Para retomarlo*: si el grado de entrada simple resulta insuficiente en la práctica (ej. sitios
    con navegación muy plana donde casi todo tiene el mismo grado), instalar el plugin GDS en la
    instancia de Neo4j (no viene por defecto ni en la edición gratis) y correr PageRank sobre
    `NAVIGATED_TO`/`DISCOVERED_LINK`.
- **El seed de `sitemap.xml` sigue un solo nivel de `sitemapindex`**, con un tope de 5
  sub-sitemaps — un sitio con un índice de sitemaps más profundo o más ancho no se cubre por
  completo con este mecanismo (aunque el crawling real igual lo termina descubriendo, solo pierde
  el atajo gratuito).
- **`_order_pending` recalcula `finished_sections` en cada iteración de la fase esqueleto**
  llamando a `get_progress_table_rows` (trae todas las filas, no solo las `Finished`) — en un sitio
  con miles de páginas ya visitadas esto podría empezar a pesar. No se optimizó porque no hay
  evidencia todavía de que sea un problema real a la escala de sitios que este proyecto crawlea hoy.

## Modo seguro (safe mode)

- **Es una heurística aproximada, no una garantía.** `classify_mutation_risk` solo puede ver dos
  señales del DOM (método del formulario, texto del componente) - no hay forma de conocer el
  efecto real de un handler de JS (un `onClick` que llama a una API) desde análisis estático. Un
  botón de verdad mutante con texto genérico ("Listo", "Ok", "→") y sin `<form>` real no se
  detecta hoy.
- **El vocabulario de verbos (`_MUTATION_VERBS`) es una lista fija, mantenida a mano** - un sitio en
  otro idioma (no español/inglés) o con verbos de negocio fuera de la lista no se detecta. Extender
  la lista es fácil pero manual.
- **No intercepta tráfico de red real** - la alternativa más precisa (ver la entrada nueva en
  `feedback.md`: interceptar el JS/requests reales vía `page.route()`/`page.on('request')` de
  Playwright) daría una señal mucho más confiable de qué es un GET/POST real, en vez de inferirlo
  de atributos del DOM. Quedó fuera de esta implementación porque cambia la forma de discovery en
  sí, no es una extensión chica del guard actual.
- **Un formulario GET que en la práctica sí muta estado** (mal implementado, pero existe en la
  vida real) no se detecta - la señal estructural asume que la convención HTTP GET=no-mutante se
  respeta, que no siempre es cierto.

## General (no ligado a una fase puntual)

- **Instrumentación/métricas de la corrida**: no hay ningún resumen que compare, en una corrida
  real, cuánto ayudó cada mecanismo (cuántas iteraciones se gastaron en la fase esqueleto vs.
  profundidad, cuántas páginas se dedupearon por identidad de URL, cuántos componentes quedaron
  excluidos de deuda por agrupación). Todo lo construido en esta sesión tiene test unitario, pero
  no se corrió todavía contra un sitio real para confirmar la mejora empírica más allá de lo que
  los tests garantizan por diseño.
- **`tests/test_neo4j_graph_store_integration.py` no se actualizó** con casos para
  `get_incoming_link_counts` (Fase 2) ni para `excluded_from_debt` en `record_component_options`
  (Fase 3) - esos métodos solo están probados contra `InMemoryGraphStore`. La query Cypher se
  escribió siguiendo el mismo patrón que el resto del archivo, pero no se verificó contra una
  instancia Neo4j real (no había una disponible en el entorno donde se implementó esto).

## Cómo usar este documento

Cuando se retome cualquiera de estos puntos: implementarlo, y **mover** esa entrada de acá al
commit correspondiente (no dejarla duplicada en los dos lugares). Si en el camino aparece un
residuo nuevo, agregarlo acá siguiendo el mismo formato (qué falta + por qué se dejó afuera), no
solo como un comentario suelto en el código.
