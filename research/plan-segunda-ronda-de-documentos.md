# Plan: segunda ronda de documentos sobre el grafo Ladybug

Continuación de `plan-generacion-de-documentos.md` (D1–D12), después de la migración de
almacenamiento a Ladybug. Ese plan sigue siendo la referencia para qué es cada entregable; este
cubre sólo lo que la migración cambió: lo que habilitó, lo que rompió y lo que borró.

**El diagnóstico en una línea: el camino de escritura se adelantó al de lectura.** La migración
agregó `Interaction` como nodo, `Container`/`CONTAINS`, `Option`, `Payload`, `Endpoint`, las
métricas de proyección y tres tiers con trazabilidad. Casi nada de eso llega hoy a un documento.
Los generadores consumen los mismos diez métodos de lectura que consumían antes.

---

## 0. Estado: qué de este plan ya shippeó

Marcado contra lo que realmente entró, en la rama `claude/architecture-docs-review-7a25cd`.

| Ítem | Estado | Nota |
|---|---|---|
| A1 — regresión de `option_labels` en D5 | **hecho** | Se derivan con `describe_options_from_rows`; el fixture pasó a la forma real del ledger |
| A2 — lectura de `Container`/`landmark` | **hecho** | `get_component_regions()`; D5 reporta regiones, D2 anida por región |
| A3 — lectura de métricas de proyección | **hecho** | `get_page_metrics()`, una consulta para métricas y módulo |
| A4 — bodies como ejemplos en D4 | **hecho** | `request_example`/`response_example`; el de respuesta sólo desde un 2xx |
| A5 — integraciones de terceros | **hecho** | Sección de D13, no de D4: el OpenAPI es YAML y no admite prosa |
| Fase C — PRD por módulo | **hecho** | `group_pages_by_module`; además cita profundidad y puntos de articulación |
| D13 — mapa de arquitectura | **hecho** | `generators/architecture_map.py`, registrado como `architecture` |
| B1 — recuperar D10 (tokens) | **hecho** | Recuperado del historial; los estados `:hover`/`:focus` volvieron después, en el nivel 2 |
| B2 — accesibilidad (D11) | **hecho, parcial** | Nivel 1 abajo: sin axe, sólo lo que los datos prueban. Reemplaza la decisión original de no hacerlo |
| B3 — limpiar D7 | **hecho** | Regla `unattributable-outcome` borrada; la referencia a tokens volvió a ser cierta con B1 |
| Fase D — tier semántico + D14 | **hecho** | `semantic.py` con provenance obligatoria; D14 = `data-model` |
| D15 — reglas de negocio | **sigue congelada** | Misma razón que la Fase 7 del plan anterior |
| Fase E — docs de desarrollo | **hecho** | 19 archivos escritos, 44 anclas rotas arregladas, 2 huérfanos borrados, `tests/test_dev_docs.py` lo sostiene |

**Lo que se descubrió al ejecutarlo y no estaba en el plan:**

- El motor Ladybug no corre en Windows sin bajar `lbug_shared.dll` del release del
  proyecto; el wheel trae sólo la estática. Nada en el repo lo decía. Con eso resuelto, la
  suite pasó de "no colecciona" a verde.
- Ocho tests fallaban por *test doubles* con la firma previa a la migración (`site` como
  argumento). El código de producción estaba bien.
- `DERIVED_FROM` no declara ningún par que llegue a `Request`, así que D14 deriva sólo de
  formularios. Agregar el par es una línea de DDL **más** una historia de migración:
  `CREATE REL TABLE IF NOT EXISTS` no altera una tabla existente.
- Los ciclos de navegación se calculan en cada corrida y no se persisten en ninguna parte.
- La deuda de `docs/dev/` era peor de lo contado: 19 archivos faltantes **y** 44 punteros
  apuntando a encabezados inexistentes en archivos que sí existen.

---

## 1. Estado real de cada dato capturado

Verificado contra el código, no contra los planes.

| Dato en el grafo | Se escribe | Se puede leer | Lo consume algún documento |
|---|---|---|---|
| `Page`, `Component`, ledger, edges | sí | sí | sí (todos) |
| `Interaction` como nodo (`visit_id`/`step_seq`) | sí | sí | sí — arregló la atribución en D6 |
| `Endpoint` + `auth_scheme`/`status`/`media_type`/`latency` | sí | sí | **sí, ya shippeado** en D4 |
| `Option` (miembros de un choice-group) | sí | sí (`record["options"]`) | D2 y D1 sí; **D5 no** (ver A1) |
| `Container` + `landmark` + `CONTAINS` | sí | **no** (sólo `components_in(container_id)`, y no hay forma de descubrir un `container_id`) | no |
| `Payload` (bodies redactados + `byte_length`) | sí | **no** (`InferredRequest` no los expone) | no |
| Métricas y módulos de `Page` (`module_label`, `click_depth`, `betweenness`, `pagerank`, `is_articulation_point`) | sí, cada corrida | **no** (`analysis.py` sólo tiene `record_*`) | no |
| Tier semántico (`Screen`/`Entity`/`Field`/`Flow`/`Rule`, `DERIVED_FROM`) | **no** (sólo DDL) | — | no |
| Superficie de recuperación (`raw()`, `query()`, `search_text()`, `schema_card()`) | — | sí | no |
| Terceros (`integrations()`) | sí | sí | no |

Las filas con "no" en la columna del medio son el trabajo más barato del plan: el dato ya se paga
en cada corrida y hoy se tira.

---

## 2. Fase A — Cerrar la brecha lectura/escritura

Cero captura nueva. Cada ítem es un método de lectura (o un consumidor mal migrado) y el documento
que cambia cuando existe.

### A1 — D5 perdió los `option_labels` (regresión, no mejora)

`component_catalog.py:41` declara `option_labels` como prop del catálogo y `_props`
([component_catalog.py:137](generators/component_catalog.py:137)) lo busca con
`member.get("option_labels")`. El ledger de hoy no entrega esa clave: entrega
`record["options"]` como `(rows, group_name)`, y quien quiere la forma normalizada llama
`describe_options_from_rows(*record["options"])`. `component_tree.py:107` y
`graph_prd_synthesizer.py:112` sí se migraron a eso; **el catálogo no**. Resultado: el prop
`option_labels` está siempre ausente, así que todo dropdown, `select` y choice-group del catálogo
salió sin sus opciones desde la migración.

No lo agarró ningún test porque el fixture de `test_component_catalog.py:16` construye el member a
mano con `"option_labels": []` — codifica la forma vieja del ledger, no la real.

Arreglo: en `build_catalog`, derivar las etiquetas con `describe_options_from_rows` antes de armar
los props, y corregir el fixture para que use la forma que devuelve el ledger. Es el ítem más
chico del plan y el único que repara algo roto.

### A2 — `Container`/`landmark` desbloquea moléculas y organismos en D5

El plan anterior anotó este techo con su propia salida: *"Sin organismos ni plantillas: fuera de
alcance por decisión, no por imposibilidad — Sí: capturar el ancestro landmark (1 línea de JS)"*.
Ese JS existe: `discover_components.js::structuralAncestorsOf` calcula el rol landmark implícito
(`landmarkOf`, línea 123) y `containment.py` lo persiste en `Container.landmark`.

Falta el método de lectura. Con uno que devuelva, por página, los contenedores con su `landmark` y
los componentes que cada uno contiene (`CONTAINS*`), D5 puede:

- Agrupar el catálogo por región real (`nav`, `main`, `contentinfo`, `search`) en vez de listar
  átomos planos.
- Nombrar moléculas por co-ocurrencia: un `Container` que contiene siempre input + botón es un
  campo de búsqueda, y eso sale de una consulta, no de una opinión del modelo.
- Dar a D2 (árbol) la jerarquía verdadera en lugar de la del selector CSS.

Nota de diseño: `containment.py` guarda sólo aristas directas a propósito, así que cualquier
consulta de ancestría es `CONTAINS*1..n`, no un lookup. El método nuevo tiene que asumir eso.

### A3 — Las métricas de proyección no las lee nadie

`Engine._apply_graph_projection` corre `project_graph` cada corrida y escribe seis columnas en
`Page` ([engine.py:112](core/engine.py:112)). `analysis.py` expone `record_page_metrics` y
`record_page_modules` y ningún `get_*`. Hoy se paga networkx sobre todas las aristas y no hay
documento que muestre un módulo, una profundidad ni un cuello de botella.

Un `get_page_metrics()` habilita dos cosas distintas:

1. **D13 (nuevo) — Mapa de arquitectura.** Los módulos detectados con su nombre, la profundidad de
   clic de cada página, los puntos de articulación (páginas sin ruta alternativa alrededor) y los
   ciclos de navegación. Es el documento que responde "de cuántas partes está hecha esta
   aplicación", que hoy no responde ninguno.
2. **La reestructuración de D1** — ver Fase C, que es donde más rinde.

### A4 — Los bodies redactados habilitan ejemplos en D4

`network_filter` captura request/response bodies redactados y truncados a 8KB, y `network.py:148`
los guarda como `Payload` con su `byte_length` real previo al truncado. `InferredRequest` no tiene
campo para ellos, así que `openapi.py` sigue publicando shapes sin ejemplos.

El plan anterior listaba esto como techo permanente: *"Sin `securitySchemes`, headers ni ejemplos —
el crawler guarda shapes, no valores | No sin romper la decisión de privacidad"*. La decisión de
privacidad cambió de forma, no de fondo: hoy hay dos capas de redacción
(`spiders/content/redaction.py`, claves sensibles descartadas por nombre + escaneo de patrones para
emails, tarjetas y tokens; `Authorization`/`Cookie` descartadas enteras). Un ejemplo redactado es
publicable donde un valor crudo no lo era. `securitySchemes` ya se resolvió y está en producción.

Trabajo: exponer los bodies en la lectura de endpoints y usarlos como `example` en el OpenAPI.
**Antes de publicar, revisar a mano la salida de un sitio real** — la redacción está testeada
(`tests/test_redaction.py`, 16 casos) pero un ejemplo es lo único de este pipeline que sale con
datos parecidos a datos.

### A5 — `integrations()` no aparece en ningún documento

La query existe y devuelve los `Endpoint` de terceros ordenados por volumen de llamadas. Es una
sección corta en D4 o en D13: con quién habla esta aplicación que no controla. Para una
modernización, la lista de integraciones a reemplazar es una de las primeras preguntas y hoy el
dato está guardado sin consumidor.

---

## 3. Fase B — La pista de UX/UI que se borró

El commit `08078b2` borró el pase de medición y con él tres generadores. La lista `documents` pasó
de once nombres a nueve. El motivo era correcto — `measurement_pass` venía en `false` por default,
así que una corrida normal generaba D10 y D11 **desde la nada** — pero el resultado neto es que hoy
no hay documento de tokens ni de accesibilidad.

Lo importante: los dos no están en la misma situación.

### B1 — D10 (design tokens) vuelve sin el pase de medición

El propio docstring del generador borrado lo dice: *"Colours and font sizes are computed CSS
values, independent of viewport size and of the crawl's blocked images, so the palette and the type
scale are real."* El espaciado ya estaba deliberadamente ausente, por viewport-dependiente. Sólo
`build_state_tokens` (estados `hover`/`focus`) leía `get_page_measurements`.

Y la materia prima sigue capturándose: `ComponentFacts` conserva `color`, `background_color`,
`font_size`, `font_weight`, `display`, `position`, y `discover_components.js:186` sigue leyendo
`getComputedStyle`.

Recuperación concreta:

```bash
git show 08078b2^:generators/design_tokens.py > generators/design_tokens.py
git show 08078b2^:generators/color_space.py > generators/color_space.py
```

Después: borrar `build_state_tokens` y las dos llamadas a `get_page_measurements`, reponer el
import en `core/bootstrap.py` y `"tokens"` en la lista `documents`. `color_space.py` (CIEDE2000)
entra intacto — es el que evita que el documento liste 47 grises casi iguales en vez de una paleta,
y no depende de nada del pase de medición.

Alcance honesto del D10 recuperado: paleta, escala tipográfica y variantes por familia. Sin grilla
de espaciado y sin estados. El documento tiene que decirlo en su propio encabezado, no dejarlo
implícito.

### B2 — D11 (accesibilidad): decisión go/no-go, no tarea

Este sí depende del pase. De sus tres partes, `build_axe_findings` y `keyboard_findings` leen
`get_accessibility_violations`/`get_page_measurements`, que ya no existen; sólo
`undersized_targets` lee geometría del ledger — y la geometría está medida a 800×600 con
`block_images`, así que el umbral de 44 px no es confiable. Es exactamente el "umbral absoluto"
que el plan anterior separó del "relativo".

Tres caminos, en orden de coste:

1. **No hacerlo.** D7 (Nielsen) ya cubre parte del terreno con reglas deterministas y evidencia.
   El proyecto queda sin auditoría WCAG y hay que decirlo en el documento maestro, no callarlo.
2. **Revivir el pase de medición sólo por muestra**, como estaba diseñado: una página por
   `route_shape`, sin interacciones, viewport 1280×800, `block_images` desactivado. Eso devuelve
   D11 completo y de paso la grilla de espaciado de D10 y los estados. Es la única parte cara del
   plan; vendorizar axe son 540KB otra vez.
3. **Reglas propias sin axe.** El plan anterior ya lo evaluó y lo descartó con una razón que sigue
   valiendo: el contraste calculado desde `background_color` da `rgba(0,0,0,0)` para casi todo
   elemento cuyo fondo pinta un ancestro. Daría resultados mal a escala.

Mi recomendación: (1) ahora, (2) cuando la auditoría de UX pase a ser entregable de primera línea.
No (3).

### B3 — Limpiar lo que la migración dejó colgando en D7

Dos cosas chicas en `usability.py`:

- `flow_findings` filtra por `t.outcome == "mixed"` ([usability.py:239](generators/usability.py:239))
  para emitir `unattributable-outcome`. `user_flows` eliminó `MIXED`: `_request_outcome` sólo
  devuelve `OK`/`ERROR`/`UNKNOWN`. La regla no puede dispararse y ya no hay test que la cubra. Es
  el residuo correcto de una mejora real — la atribución por interacción volvió innecesaria la
  regla — pero hay que borrarla, no dejarla.
- La recomendación de `inconsistent-family-styling` dice *"the design-token document lists the
  colours actually in use"*, y ese documento no existe. Si se hace B1, la referencia vuelve a ser
  cierta; si no, hay que reescribirla.

---

## 4. Fase C — D1 (PRD) estructurado por módulo, no por página

El cambio de mayor impacto sobre el PRD, y depende sólo de A3.

Hoy `synthesize()` lee cuatro cosas (ledger, progress rows, edges, descriptions), narra **una
llamada por página** y después reduce de a ocho secciones
([graph_prd_synthesizer.py:307](generators/graph_prd_synthesizer.py:307)). Para un sitio de cuarenta
páginas el resultado es una lista plana agrupada por nada: el orden de las secciones lo decide el
tamaño del lote de reduce, no la aplicación.

Con `get_page_metrics()` disponible, el reduce puede agrupar por `module_label` y ordenar por
`click_depth`. El PRD pasa de "cuarenta páginas descriptas en el orden en que se descubrieron" a
"seis módulos, cada uno con sus páginas de la más superficial a la más profunda". Es la misma
cantidad de llamadas al modelo y la misma información; cambia sólo el agrupamiento, que es
justamente lo que un PRD necesita para ser legible.

Dos mejoras que vienen de arrastre y no cuestan llamadas nuevas:

- **Citar la profundidad y los puntos de articulación en la prosa.** "Esta página es el único
  camino a las otras cuatro del módulo" es un hecho estructural que hoy el modelo no tiene y no
  puede inventar bien.
- **Nombrar los módulos con el label determinista, no pedirle al modelo que agrupe.** El
  agrupamiento sale de networkx; el modelo escribe prosa sobre un agrupamiento ya decidido. Es la
  misma división de trabajo que ya usan D5 y D7: clustering determinista, narración encima.

---

## 5. Fase D — El tier semántico, con trazabilidad obligatoria

`schema.py` declara `Screen`, `Entity`, `Field`, `Flow`, `Rule`, sus seis aristas y
`DERIVED_FROM {method, confidence, run_id, generator}`. No hay writer: el módulo que su propio
comentario nombra (`semantic.py`) no está en el paquete. Es el step 10 del plan de almacenamiento.

Esto es lo que habilita documentos que hoy son imposibles, no sólo mejores:

- **D14 — Modelo de datos.** `Entity` + `Field` + `EDITS` a los `Component` que los editan: qué
  entidades maneja la aplicación, con qué campos, tipos observados y validaciones. Sale de los
  formularios y de los shapes de request que ya están en el grafo.
- **D15 — Reglas de negocio.** `Rule` es la `:BusinessRule` que la Fase 7 del plan anterior
  congeló. Sigue congelada por la misma razón (su valor estaba casi todo en la revisión humana,
  que está fuera de alcance), pero ahora la tabla existe y el día que se descongele hay dónde
  escribir.

**La regla que hace que esto valga algo:** ningún nodo semántico entra sin al menos una arista
`DERIVED_FROM` a las observaciones que lo sostienen. Sin eso el tier semántico es una capa de
opiniones del modelo mezclada con hechos del crawl, que es exactamente lo que el esquema de tres
tiers existe para evitar. Con eso, cualquier documento puede decir "esto lo deduje, y acá está de
dónde" — y `confidence`/`generator` permiten que un documento marque sus propias afirmaciones
flojas, en el mismo espíritu que el banner de cobertura.

Prerrequisito de orden: D14 y D15 van **después** de la Fase A. Escribir el tier semántico antes de
poder leer `Container`, `Payload` y las métricas significa deducir entidades sin ver la estructura
que las agrupa.

---

## 6. Fase E — Los docs de desarrollo

`docs/dev/README.md` fija la política: cada archivo bajo un paquete Python tiene un `.md` espejo en
la misma ruta relativa, con headings nombrados como el símbolo que documentan, y *"touch the doc
file in the same change that touches the code"*. La migración no la cumplió.

**22 referencias `Details:` apuntan a archivos que no existen** — verificado recorriendo cada
puntero del código:

- Los 16 de `docs/dev/database/ladybug/*.md` (todo el paquete nuevo: `store`, `schema`, `writer`,
  `page`, `component`, `network`, `options`, `containment`, `named_queries`, `raw_query`, `search`,
  `analysis`, `component_family`, `text_content`, `ids`, `clock`, `_cypher`).
- `docs/dev/analysis/graph_projection.md`, `docs/dev/core/caching_graph_store.md`,
  `docs/dev/spiders/content/redaction.md`, `docs/dev/spiders/content/payload_capture.md`,
  `docs/dev/spiders/orchestration/mechanical_loop/budget.md`.

En la dirección contraria, `docs/dev/database/memory_graph_store.md` documenta un módulo borrado, y
el índice del README todavía lo lista junto a los `neo4j_*` que ya no están.

Orden sugerido, por rendimiento:

1. **`schema.md` y `store.md` primero.** Son los dos que un recién llegado necesita para entender
   el resto, y ahora que `ARCHITECTURE.md` describe el esquema real, el doc de módulo puede quedarse
   en el "por qué" de cada decisión sin repetir la ontología.
2. **`named_queries.md`, `raw_query.md`, `search.md`.** Son la superficie que un consumidor externo
   (o un modelo) va a tocar; documentarlas es prerrequisito honesto de la Fase D del plan de RAG
   (`rag-over-neo4j-for-future-qa.md`).
3. **El resto de los mixins**, que son mecánicos.
4. **Borrar `memory_graph_store.md`** y regenerar la tabla del índice desde el árbol real.

Vale un chequeo automatizable, no una revisión a ojo: recorrer los `Details:` del código y fallar
si alguno apunta a un archivo inexistente. Es la clase de regla que se rompe sola en la próxima
migración.

---

## 6.5 Recuperar lo que se dejó de hacer: tres niveles

De los 16 documentos que alguna vez estuvieron registrados, **uno solo había dejado de
producirse**: `accessibility` (D11). `tokens` (D10) había caído en el mismo commit y volvió en
B1. Aparte de eso, tres pérdidas *dentro* de documentos que sí se seguían haciendo: D10 sin
escala de espaciado, D10 sin estados de interacción, y D13 sin ciclos de navegación.

Ordenados por costo, no por importancia.

### Nivel 1 — D11 determinista, sin axe y sin captura nueva — **hecho**

Lo que lo hace posible ahora y no antes:

- **`Container.landmark` + `get_page_landmarks()`** convierten la estructura de landmarks en
  una propiedad consultable de la página. Antes eso sólo lo veía un navegador.
- **La cadena de nombre accesible ya se resuelve en captura.**
  `discover_components.js` calcula `text` como
  `innerText || aria-label || aria-labelledby || title || img[alt] || svg>title`, y la
  asociación con `<label>` aparte en `label`. Un control sin nada después de todo eso **es**
  un hallazgo, no una heurística.

Cuatro reglas: `missing-accessible-name` (4.1.2), `placeholder-as-only-label` (3.3.2),
`no-main-landmark` (2.4.1), `duplicate-unique-landmark` (1.3.1).

Lo que costó una decisión y no una línea de código:

- El `innerText` de un `<input>` es siempre vacío, así que su nombre sale de `label` o de
  `aria-label`. Una regla que mirara sólo `text` daría falso positivo en **todos** los campos
  correctamente etiquetados del sitio.
- Un elemento produce un solo hallazgo de nombre: la regla específica gana, porque el arreglo
  difiere (promover el placeholder vs. inventar un nombre).
- `navigation` no es un landmark único. Varios `<nav>` es markup correcto.
- Las páginas sin ancestría registrada no se juzgan: "no tiene `main`" y "no se capturó
  containment" son afirmaciones distintas.
- La capa `cursor: pointer` se saltea **y se cuenta en el documento**. Un `div` clickeable sin
  nombre es una falla real y un wrapper decorativo no lo es; el crawl no los distingue, así que
  el punto ciego se declara en vez de aplicarse en silencio.
- La nota de alcance se renderiza **siempre**, incluso sin hallazgos. La salida peligrosa acá es
  la limpia: una auditoría parcial que no dice que es parcial se lee como "esta aplicación es
  accesible", que es justo lo que no verificó.

Los hallazgos no se guardan, igual que D7: se recalculan cada corrida, el documento es su único
consumidor, y los nodos `Rule` con `DERIVED_FROM` están ahí para el día que aparezca un segundo.

### Nivel 2 — los estados de interacción de D10 — **hecho, y más barato de lo estimado**

La estimación era "captura modesta". Resultó **ningún pase nuevo**.

`extract_pseudo_styles.js` lee `document.styleSheets` y matchea las reglas declaradas contra
elementos en reposo. No hace hover, no necesita CDP, no lee geometría — así que **no depende del
viewport ni de que carguen las imágenes**, exactamente como los colores y los tamaños de fuente.
Vivía en el pase de medición por dónde lo pusieron, no por lo que necesitaba. Y el crawl no
bloquea CSS (`_BLOCKED_RESOURCE_TYPES` es `{image, media, font}`), así que corre en el pase de
descubrimiento normal.

Almacenamiento: tabla `StateStyle` nueva + `HAS_STATE_STYLE`. Una tabla **nueva** es libre de
migración porque `connect()` corre el DDL en cada apertura, a diferencia de extender la lista
`FROM`/`TO` de una tabla existente — que es lo que bloquea derivar entidades desde `Request` en
D14. Vale tenerlo presente: la asimetría decide qué cambios de esquema son baratos.

Un bug que un test agarró: el read traversaba `HAS_COMPONENT`, y un componente que sólo existe
por el `MERGE` defensivo del write no tiene esa arista — los estilos se guardaban y quedaban
ilegibles, lo que volvía falso el motivo declarado del `MERGE`. Ahora la página sale de
`split_component_id`.

### Nivel 3 — lo que sigue necesitando el pase de medición — **pendiente, go/no-go**

Acá la tecnología nueva no ayuda: el problema es de captura, no de almacenamiento. Nada de esto
se puede derivar de lo que hay en el grafo.

| Falta | Por qué no se puede hoy | Documento afectado |
|---|---|---|
| Ratios de contraste (WCAG 1.4.3) | `background_color` devuelve `rgba(0,0,0,0)` para casi todo elemento cuyo fondo pinta un ancestro. Es la razón por la que se eligió axe en lugar de reglas propias, y sigue valiendo | D11 |
| Tamaño de objetivo táctil (2.5.8) | Umbral absoluto (24px) contra geometría medida a 800×600 con imágenes bloqueadas | D11 |
| Foco visible y orden de tabulación (2.4.7, 2.4.3) | Requiere recorrer la página con `Tab` durante el crawl | D11 |
| Escala de espaciado | Misma geometría a 800×600 | D10 |
| El resto de WCAG (~90 reglas de axe) | Vendorizar axe-core son 540KB y un pase que visite cada página con viewport realista | D11 |

**La regla transversal que gobierna todo esto y ya está escrita en el documento maestro: las
comparaciones relativas sobreviven ese viewport, los umbrales absolutos no.** "Estos tres
botones no coinciden entre sí" es cierto igual; "este botón mide menos de 24px" no.

El diseño del pase, si algún día se hace, ya está especificado en
`plan-generacion-de-documentos.md` §5.0: una página por `route_shape`, sin interacciones,
viewport 1280×800, `block_images` desactivado. Es una fracción del crawl original, no su
duplicación.

**Aparte y mucho más barato: los ciclos de navegación de D13.** `project_graph` ya los enumera
en cada corrida y se descartan. No necesita pase de medición, sólo una tabla o pasarlos por
`DocumentRequest.settings`. Queda pendiente por proporción, no por dificultad.

---

## 7. Techos nuevos

Lo que sigue sin poder hacerse, para no descubrirlo con el documento entregado. Reemplaza las filas
de D10/D11 de la tabla del plan anterior.

| Documento | Techo | ¿Se levanta? |
|---|---|---|
| D10 tokens | Sin grilla de espaciado: la geometría está medida a 800×600 con `block_images` | Sí, con el pase de medición (B2 opción 2) |
| D10 tokens | Sin estados `hover`/`focus`/`active` | Sí, mismo pase |
| D11 WCAG | No existe hoy | Sólo con B2 opción 2; las reglas propias ya se descartaron con razón |
| D4 OpenAPI | Los ejemplos dependen de que la redacción sea correcta, y es lo único que publica datos parecidos a datos | Mitigable con revisión manual, no eliminable |
| D5 catálogo | Los nombres de dominio los sigue poniendo el modelo | Parcialmente: A2 da regiones deterministas donde antes había sólo nombres inventados |
| D13 mapa | Los módulos son de la parte del sitio que el crawl alcanzó; un módulo sin visitar no aparece | Sí: más cobertura (lo reporta D9) |
| D14 modelo de datos | Entidades deducidas de formularios y shapes, no del modelo de datos real del backend | No sin acceso al backend |
| Todos | Superficie pública: el crawl no se autentica (H3 sigue abierto, `login_helper` sigue huérfano) | Sí: credenciales |

---

## 8. Orden recomendado

```
A1 (regresión de option_labels)     ─┐
A3 (get_page_metrics)                ├─→ sin dependencias entre sí, cualquier orden
A5 (integrations en D4/D13)         ─┘

A2 (lectura de Container)  ──→ D5 con regiones, D2 con jerarquía real
A3                         ──→ Fase C (PRD por módulo)  ──→ D13 (mapa de arquitectura)
A4 (bodies)                ──→ ejemplos en D4  [revisión manual antes de publicar]

B1 (recuperar D10)         ──→ B3 (la referencia colgada vuelve a ser cierta)
B3 (borrar la regla muerta) ─── independiente, hacerlo con B1 o antes

B2 ── decisión, no tarea. Bloquea D11, la grilla de D10 y los estados.

Fase A completa ──→ Fase D (tier semántico con DERIVED_FROM) ──→ D14, D15
Fase E ── en paralelo con todo; `schema.md`/`store.md` primero
```

Lo más barato con más rendimiento: **A1, A3 y la Fase C**. A1 repara una pérdida silenciosa, A3
convierte trabajo que ya se paga en dato legible, y la Fase C mejora el documento más visible del
proyecto sin una sola llamada extra al modelo.
