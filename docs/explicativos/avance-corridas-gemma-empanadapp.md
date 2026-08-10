# Avance: corridas locales contra empanad.app (comparación de modelos)

> Notas de avance, no un documento de diseño — pensado para completarse con cada modelo nuevo que
> se pruebe, así queda un registro comparable de qué dio cada uno. Escrito analizando lo que quedó
> en disco en el checkout sin worktree (`C:\Users\Julieta\projects\pragma`), no en una corrida propia.

## Qué se corrió

- **Sitio**: `https://www.empanad.app` (recorrido completo, sitio con flujo de pedido por sesión
  `/o/<hash>` — cada visita mintea una orden nueva, comportamiento ya documentado en
  `wiki/graph-based-crawl-tracking.md`).
- **Config** (`pragma.yaml` en el checkout, no versionado): `agent: local`, `graph_store: neo4j`,
  `headless: false`, `wait_seconds: 15.0`.
- **Modelo del agente `local`**: acá hay una discrepancia a resolver antes de comparar nada -
  **`pragma.yaml` tiene `agents.local.model: qwen/qwen2.5-coder-7b-instruct`**, que pisa el
  `LOCAL_MODEL="google/gemma-4-e4b"` de `.env` (la precedencia real es
  `pragma.yaml` > env var - ver `ARCHITECTURE.md`/`src/agents/providers.py`). Si lo que estaba
  cargado del lado del servidor (LM Studio vía el túnel de Tailscale) era efectivamente gemma-4,
  probablemente el campo `model` del payload no importó (muchos servidores tipo LM Studio ignoran
  ese campo y sirven lo que tengan cargado) - pero si el servidor sí lo valida, la corrida pudo
  haber ido contra qwen2.5-coder-7b, no contra gemma. **Antes de la próxima corrida, confirmar cuál
  de los dos estaba realmente sirviendo** (o, más simple, alinear `pragma.yaml`'s
  `agents.local.model` con lo que se quiera comparar cada vez, para que no dependa de qué haya en
  `.env`).
- **`agents.local.max_tokens: 8192`** (`pragma.yaml`) - dato clave, ver abajo.

## Qué se generó (4 intentos, todos con el mismo resultado)

Cuatro corridas completas en `debug_logs/www.empanad.app__<timestamp>/`, todas hoy (2026-08-09),
separadas por 17-53 minutos entre sí:

| Corrida (UTC) | Duración del crawl | Hooks logueados | Interacciones intentadas | Errores reales |
|---|---|---|---|---|
| 20:51:27 | ~16 min | 195 | 28 | 2 ("element not found", recuperado, no fatal) |
| 21:44:54 | ~16 min | 195 | 28 | 2 (idem) |
| 22:02:07 | ~16 min | 195 | 28 | 2 (idem) |
| 22:24:20 | ~16 min | 195 | 28 | 2 (idem) |

**Las cuatro son prácticamente idénticas** (mismo conteo de hooks, mismas 4 URLs de sesión
visitadas, mismo patrón de interacción) - el crawl en sí es determinístico (la nueva arquitectura
`crawl4ai`/`MechanicalCrawler` no usa al LLM para decidir qué clickear, solo para el valor de campos
de texto y para la síntesis final), así que repetir la corrida contra el mismo sitio produce
esencialmente el mismo recorrido cada vez. Contenido real capturado, de calidad (ver
`debug_logs/.../pages/www.empanad.app_o_*.md`): nombre del pedido, sabores de empanadas, estado de
confirmación por persona, división de cuenta - el crawl está andando bien.

**Ninguna de las 4 generó salida en `docs/`** (ni PRD ni tree ni export) - ni un solo archivo. Eso es
lo que "se truncó por maxtokens" describe.

## Análisis: dónde se cortó, con evidencia (no solo la sensación de que pasó)

El crawl (fase 1: `MechanicalCrawler.crawl_site`) **se completa exitosamente las 4 veces** - el
`debug.md` de cada corrida termina en un guardado de página normal, sin señal de corte abrupto, y
los 2 errores reales por corrida son "element not found" ya manejados con gracia por el propio loop
(reintenta, sigue, no aborta - comportamiento documentado y esperado). No hay ningún rastro de
`max_tokens`/truncamiento dentro de `debug.md` en ninguna de las 4 corridas.

Eso señala a la fase 2 (`GraphPRDSynthesizer.synthesize`, en `src/generators/graph_prd_synthesizer.py`),
que **no deja ningún rastro en `debug_logs/`** (ese logging es solo para hooks de `crawl4ai`, no para
llamadas al agente) - consistente con que el crawl completo pero la corrida entera murió sin escribir
nada a `docs/`. Dentro de esa fase hay dos tipos de llamada al agente:

- **Narración por página** (`_narrate_page_catalog`): tiene try/except propio, una falla ahí degrada
  a mostrar los hechos crudos en vez de prosa - **no puede ser la causa** de que no se generara nada.
- **Síntesis final** (una sola llamada `agent.generate(...)` que arma el Blueprint completo a partir
  de todas las páginas narradas + el grafo de navegación en Mermaid): **sin try/except**, y es el
  prompt más grande de todo el pipeline por lejos. Si esta llamada tira una excepción, se propaga sin
  atajarse hasta `cli.py`, que imprime `"Critical error during exploration: ..."` y no escribe nada.

`src/agents/local_agent.py::LocalAgent._raise_if_truncated` levanta exactamente ese tipo de error
(`RuntimeError: Response truncated: the model hit max_tokens before finishing (finish_reason:
'length')`) cuando el servidor corta la respuesta por `max_tokens` - y `pragma.yaml` tiene
`agents.local.max_tokens: 8192`, un límite bastante ajustado para pedirle a un modelo chico que arme
un documento completo (overview + estructura de navegación + catálogo de componentes narrado de
varias páginas + el diagrama Mermaid) en una sola respuesta.

**Conclusión (inferencia razonable a partir de la evidencia disponible, no confirmada con el error
real en pantalla - no quedó ningún log de terminal guardado)**: la síntesis final probablemente pisó
el techo de `max_tokens: 8192` con el modelo usado. El crawl en sí no es el problema.

## Recomendaciones antes de la próxima corrida (con el modelo nuevo)

1. **Confirmar qué modelo estaba realmente sirviendo** en la corrida de gemma (ver discrepancia
   `pragma.yaml` vs `.env` arriba) - si no se puede confirmar, alinear `pragma.yaml`'s
   `agents.local.model` explícitamente a lo que se quiera probar cada vez, para que la comparación
   entre modelos sea real.
2. **Subir (o sacar del todo) `agents.local.max_tokens`** antes de repetir con cualquier modelo chico
   - la propia guía del código lo dice: *"raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in
   pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs"*.
   Sacarlo del todo (comentar la línea en `pragma.yaml`) es la opción más simple para no tener que
   adivinar un número.
3. **No hace falta re-crawlear para diagnosticar esto** - el crawl ya está probado y funciona igual
   las 4 veces. Si se quiere ahorrar los ~16 minutos de crawl mientras se ajusta el modelo/límite de
   tokens, y el grafo sigue vivo en Neo4j (`graph_store: neo4j`, y no se corrió con `--fresh` de por
   medio entre intentos - a confirmar), se podría en teoría invocar solo la síntesis contra el grafo
   ya poblado sin recorrer el sitio de nuevo - hoy no hay un comando de CLI directo para "solo
   sintetizar" (el `Engine` siempre corre `crawl_site` + `synthesize` juntos), así que por ahora la
   forma más simple sigue siendo dejar correr todo de nuevo con el límite corregido.
4. Si se repite el patrón de fallo con el próximo modelo, **conviene guardar la salida de la terminal
   a un archivo** (`python3 src/cli.py https://www.empanad.app 2>&1 | tee run.log`, o el equivalente
   en PowerShell) - así la próxima vez el error real queda capturado en vez de tener que inferirlo
   como acá.

## Corrida 5 (modelo nuevo) — completó, con datos reales

Corrida `debug_logs/www.empanad.app__20260809T231201Z/` (23:12:01 → último hook de crawl 23:27:40 UTC,
~15.6 min de crawl - misma duración que las 4 anteriores), con la transcripción de terminal que
mandaste. Terminó bien: generó `docs/www.empanad.app__prd_20260809T232740Z.md` (4524 bytes) y
`docs/www.empanad.app__tree_20260809T232740Z.md` (18065 bytes, 150 componentes), y - esto es nuevo
desde la última vez que se corrió el proyecto - **también actualizó `docs/runs.json` y
`docs/index.md` automáticamente** (funcionalidad agregada en el plan de storage, Fases A/E - primera
vez que corre contra un Neo4j real de verdad, no solo contra los tests). Confirmado en
`docs/runs.json`: `"graph_store": "Neo4jGraphStore"` - la corrida efectivamente persistió a Neo4j, no
a la memoria del proceso.

**Importante, encontrado en el propio `pragma.yaml`/`.env` de este checkout**: ni el modelo
(`agents.local.model: qwen/qwen2.5-coder-7b-instruct`) ni `agents.local.max_tokens: 8192` cambiaron
respecto a las 4 corridas de gemma - ambos archivos están **exactamente igual** que antes. Si de
verdad se comparó gemma-4 contra un modelo distinto, el cambio tuvo que ser del lado del servidor
(qué modelo tenías cargado en LM Studio/lo que sea que sirve detrás del túnel de Tailscale, sin
actualizar `pragma.yaml` para que lo refleje) - muchos servidores tipo LM Studio no validan el campo
`model` del payload y sirven lo que tengan cargado en ese momento, así que es totalmente posible que
hayas comparado dos modelos reales sin que quede registrado en la config cuál era cuál. **Recomendación
para la próxima comparación**: actualizar `agents.local.model` en `pragma.yaml` para que coincida con
lo que realmente tenés cargado cada vez - si no, este documento no puede confirmar con certeza que la
corrida 5 haya sido un modelo distinto al de las 4 primeras, solo que *algo* cambió y esta vez
funcionó.

Otras dos observaciones de la transcripción de terminal (no relacionadas al modelo, informativas):

- **4 apariciones de `[CAPTURE]. ℹ Error capturing response details ... cannot access local variable
  'text_body' where it is not associated with a value`** - un bug real, pero de la librería
  `crawl4ai` (no está en `src/` de este proyecto - lo busqué), y **sin impacto en los datos
  guardados**: las 4 ocurrencias son sobre `favicon-32.png`/`logo.png`, y
  `src/crawlers/network_filter.py::_MEANINGFUL_RESOURCE_TYPES` ya excluye imágenes de lo que se
  considera "significativo" - esas respuestas iban a descartarse igual. No vale la pena perseguirlo.
- **Muchos ciclos `FETCH`/`SCRAPE`/`COMPLETE` repetidos sobre la misma URL** (`.../o/0t_ix9...`,
  decenas de veces, la mayoría ~30s cada uno en vez de los ~15s de `wait_seconds`) - esperable dado
  cómo funciona `MechanicalCrawler` (cada interacción sobre una página re-lee el DOM), y el ~30s en
  vez de ~15s probablemente sea `wait_seconds` (15s) + una llamada real al modelo local para generar
  un valor de campo de texto (`ai_fill_values: true` por default, no está en `pragma.yaml` así que
  sigue prendido) cuando el componente era un campo de texto/búsqueda, no un botón. No es un bug, es
  el costo esperado de pedirle al modelo un valor realista por cada campo en vez de un placeholder
  fijo - si se quiere una corrida más rápida para solo comparar calidad de síntesis, `ai_fill_values:
  false` en `pragma.yaml` la acortaría bastante sin afectar la síntesis final en sí.

## Comparación: gemma-4 (4 intentos) vs. corrida nueva

| | gemma-4 (o lo que haya estado sirviendo, ×4) | Corrida nueva (×1) |
|---|---|---|
| Crawl (fase 1) | ✅ Completa las 4 veces, 28 interacciones, 2 errores no fatales | ✅ Idéntica - mismo recorrido, mismas 28 interacciones |
| Narración por página | Sin evidencia (nunca llegó ahí, o llegó y no importa - no queda rastro) | ✅ Funcionó - el PRD tiene prosa narrada real por sección, no hechos crudos |
| Síntesis final | ❌ Nunca completó - 0/4 generó `docs/` | ✅ Completó - Blueprint coherente, con overview, diagrama Mermaid, flujo de usuario y resumen |
| Manifiesto/índice (`runs.json`/`index.md`) | No se llegó a escribir (la corrida entera aborta antes) | ✅ Se escribieron correctamente |

**Conclusión positiva**: el modelo/config de la corrida nueva efectivamente resolvió el problema de
truncamiento que bloqueaba a gemma-4 - la síntesis final, el paso más pesado de todo el pipeline,
terminó y produjo un Blueprint genuinamente legible y bien estructurado (ver el PRD completo). No es
solo "no truncó" - la prosa generada es correcta y describe bien lo que el crawl efectivamente
encontró (dropdowns de sabores, steppers de cantidad, botones de compartir, flujo de pago).

**Conclusión negativa / limitación real, no de un modelo en particular sino del *cutoff* de la
corrida**: la síntesis funcionó, pero **se sintetizó sobre datos muy incompletos** - `docs/runs.json`
registra `"pages_finished": 1` de `"pages_total": 4`, y `"components_unexplored": 125` de
`"components_total": 150` (**solo el 16.7% de los componentes descubiertos llegó a interactuarse**).
El propio PRD lo dice en su sección "Pending Pages": 3 de las 4 páginas quedaron sin terminar de
explorar. Esto no es un problema del modelo nuevo en sí - es que el crawl (fase 1, idéntica en las 5
corridas) nunca llegó a drenar todo lo que `www.empanad.app` tiene para ofrecer dentro de la
`element_budget`/tiempo de esta corrida. El Blueprint que generó el modelo nuevo es fiel a lo que
había disponible, pero "lo que había disponible" es una fracción chica del sitio real.

**No es un problema de storage** (el área de la que me encargo) - `GraphStore` guardó exactamente lo
que el crawl le mandó, completo y sin pérdida (ver la sección siguiente). Es una señal para ajustar
`element_budget`/`max_passes_per_page`/correr con `--no-fresh` en una segunda pasada para seguir
drenando el mismo grafo, del lado de la config de crawl - fuera de mi alcance para tocar directamente,
pero vale que quede anotado acá para quien siga esa parte.

## Qué tanto contexto y datos se están guardando (chequeo directo de mi tarea)

Preguntaste específicamente esto, así que lo reviso directo contra lo que produjo la corrida nueva:

- **`docs/runs.json`** (Fase A del plan de storage): se escribió correctamente, con `graph_store:
  "Neo4jGraphStore"` confirmando persistencia real (no en memoria) - primera confirmación en
  producción de que el manifiesto funciona contra un Neo4j de verdad, cosa que no pude probar yo
  mismo (sin Docker Desktop funcionando en mi entorno).
- **`docs/index.md`** (Fase E): igual, se generó y quedó bien formado - primera confirmación en
  producción de esa feature también.
- **`docs/www.empanad.app__tree_20260809T232740Z.md`** (150 componentes, 35 bloques de texto, 4
  páginas): esto es lo más rico de toda la corrida - capturó **network requests reales de la API de
  Supabase** (`POST .../orders`, `DELETE .../participant_selections`, con status codes reales - 201,
  200, 204) asociados al componente exacto que los disparó, más variantes completas de cada dropdown
  (el listado real de +20 restaurantes, +70 sabores de empanada, con cuál estaba seleccionado). Este
  nivel de detalle **no depende del modelo del agente en absoluto** - es la parte 100% determinística
  del pipeline (`component_classifier.py`, `network_filter.py`, `GraphStoreSink`), la misma
  arquitectura que valida el hallazgo de la sección anterior: el crawl guarda todo lo que ve, sea cual
  sea el modelo, o incluso si la síntesis final falla del todo (como en los 4 intentos de gemma - ese
  dato rico seguía ahí en Neo4j, solo que nunca se leyó para armar un documento final).
- **Conclusión sobre mi tarea**: el trabajo de storage (Fases A-E) está funcionando en un caso real,
  no solo en tests - `runs.json`/`index.md` se generaron bien, y el `GraphStore` capturó datos de
  calidad genuinamente alta (requests reales con status codes, no solo texto de botones). El cuello
  de botella de esta ronda de pruebas fue enteramente del lado de síntesis/modelo, no de
  almacenamiento - lo cual, dicho de otra forma, es una buena noticia para el área que me toca: los
  datos ricos ya estaban ahí y disponibles incluso cuando la síntesis de gemma-4 fallaba 4 de 4 veces.

## Para comparar cuando se pruebe el próximo modelo

| Modelo | ¿Completó síntesis? | `max_tokens` usado | % componentes explorados | Notas |
|---|---|---|---|---|
| gemma-4-e4b (o lo que estuviera sirviendo - ver discrepancia arriba) | ❌ No - cortó antes de escribir `docs/`, 4/4 intentos | 8192 (config sin cambios) | N/A - nunca llegó a sintetizar | Crawl siempre OK, probable techo de `max_tokens` en la síntesis final |
| Modelo nuevo (nombre real a confirmar - `pragma.yaml` sigue diciendo qwen2.5-coder-7b) | ✅ Sí, 1/1 | 8192 (config sin cambios) | 16.7% (25/150) | PRD coherente y bien narrado; el bajo % explorado es del crawl, no de la síntesis |
| _(completar con el próximo modelo)_ | | | | |

## Seguridad (encontrado de paso, ya resuelto)

Al revisar este checkout encontré `.env.example` con una API key real cargada en
`LOCAL_API_KEY` (no el placeholder vacío que tiene en `main`) y **ya estaba staged** para el próximo
commit. La desestageé y restauré el placeholder vacío - no se tocó `.env` (con las credenciales
reales, gitignorado, sigue intacto). Si se necesita esa key para el túnel de Tailscale, va en `.env`
únicamente, nunca en `.env.example`.
