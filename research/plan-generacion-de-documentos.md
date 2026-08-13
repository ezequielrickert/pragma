# Plan: generación de documentos desde el grafo

> Escrito contra `main` a la altura de `4f0c4db` (merge de `feat/component-family-inference`).
> Dos objetivos, no uno: los ocho artefactos documentales, y un grafo que se pueda leer.

## Estado de cada entregable

| # | Documento | Estándar | Estado | Fase |
|---|---|---|---|---|
| D1 | Digital Blueprint (PRD narrativo) | — | existe (`graph_prd_synthesizer.py`) | — |
| D2 | Árbol de componentes | — | existe (`component_tree.py`) | — |
| D3 | Export JSON del grafo | — | existe (`graph_export.py`) | — |
| D9 | Reporte de cobertura | — | **hecho** (`coverage.py`) | 0 |
| D4 | Contrato de API | OpenAPI 3.0 | **hecho** (`openapi.py`) | 2 |
| D5 | Catálogo de componentes (props + variantes) | Atomic Design, nivel átomo | **hecho** (`component_catalog.py`) | 3 |
| D6 | Flujos de usuario | FSM / diagrama de estados | **hecho** (`user_flows.py`) | 4 |
| D7 | Auditoría de usabilidad | Heurísticas de Nielsen | **hecho** (`usability.py`) | 5a |
| D10 | Especificación visual (design tokens) | W3C Design Tokens | **hecho** (`design_tokens.py`), sin espaciado | 5b |
| D11 | Auditoría de accesibilidad | WCAG 2.1 AA vía axe-core | falta | 5c |
| D8 | Especificación de comportamiento | BDD / Gherkin | falta | 6 |
| D12 | Documento maestro (explica y referencia a los demás) | — | **hecho** (`master_document.py`) | 0 (motor) / última etapa |

---

## 1. Veredicto sobre la investigación

Sirve como **checklist de estándares objetivo**, no como diseño. Tres bloques:

### Lo que aporta y conviene adoptar

- **La lista de artefactos con su estándar nombrado** (Gherkin, OpenAPI 3.0, Atomic Design,
  FSM/UML). Es exactamente el conjunto que falta y da un criterio de "terminado" verificable:
  un YAML que valida contra OpenAPI 3.0 o no valida.
- **La partición en tres dimensiones** (estructural / comportamental / experiencial) es una
  buena regla para decidir qué generador lee qué parte del grafo, y evita que cada generador
  vuelva a leer todo.
- **El mapeo CRUD** (método HTTP → operación de negocio) es implementable tal cual sobre
  `InferredRequest`.
- **El aviso de super-nodos** es real y ya aplica: un `:ComponentFamily` de barra de navegación
  acumula un `HAS_VARIANT` por página. Hoy no duele; con Atomic Design (Fase 3) sí.
- **`apoc.meta.data` para meter el meta-esquema en el prompt** sólo importa si se construye
  Q&A/text-to-Cypher. `research/rag-over-neo4j-for-future-qa.md` ya decidió que eso sería un
  paso de pre-retrieval y no tool-calling. No se contradicen.

### Lo que ya está hecho y no hay que rehacer

- **"Priorizar el árbol de accesibilidad sobre el DOM"**: `discover_components.js` ya hace la
  versión buena de eso — familia completa de roles ARIA, cadena de fallback de label accesible,
  shadow DOM, iframes, selectores únicos. No usamos el a11y tree de crawl4ai y no conviene
  cambiarlo (`wiki/browser-automation-pitfalls.md` documenta por qué esta lógica es intocable).
- **Correlación elemento → petición**: existe como `Component.network_requests` y como
  `(:Component)-[:TRIGGERS]->(:Request)`.
- **Idempotencia de escritura**: `MERGE` + constraints de unicidad sobre `(site, url)` y
  `(site, page_url, path)` ya están en `Neo4jGraphStore.connect()`.
- **Filtrado del ruido del DOM**: `TextContent` ya se separa de `Component`, y la capa
  `pointer` recoge los controles sin tag ni rol semántico.

### Lo que hay que descartar o corregir

- **La ontología propuesta choca con la implementada.** No renombrar nada: el mapeo importa,
  los nombres no. `:DOM_Element` ≡ el `:Component` actual, `:NetworkRequest` ≡ `:Request`,
  `:UI_Component` ≡ `:ComponentFamily` (parcialmente — le falta el nivel molécula/organismo,
  que es justo la Fase 3). El único nodo genuinamente nuevo es `:BusinessRule`.
- **Supone captura de HAR completo, WebSocket y payloads reales.** El crawler guarda sólo
  `xhr`/`fetch`, y sólo *shapes* — `network_filter._json_shape` reemplaza cada valor por su
  tipo antes de que nada llegue al grafo. Eso es una decisión de privacidad deliberada, no una
  carencia. Consecuencia dura para OpenAPI: no hay headers, ni esquema de autenticación, ni
  ejemplos. Hay que asumirlo en el generador, no "arreglarlo".
- **La heurística de latencia de Nielsen no tiene datos detrás.** Hoy no se captura ningún
  tiempo de red. Eso es captura nueva en el crawler, no una consulta al grafo (Fase 8).
- **No dice nada sobre la legibilidad del grafo.** Propone agregar nodos y relaciones, nunca
  cómo se lee el resultado. La Fase 1 existe por eso.
- **Casi cada afirmación cita "TESIS PRAGMA" como fuente 1.** Es material propio devuelto en
  otro formato: sirve de checklist, no de validación externa. Las citas externas reales
  (Nielsen, Swagger, Atomic Design) son las que aportan el estándar.

---

## 2. Qué hay hoy en el grafo

**Nodos**: `:Site`, `:Page`, `:Component` (+ etiqueta por tag: `:Button`, `:Input`, `:Link`…),
`:TextContent`, `:ComponentFamily`, `:Request`, `:RequestFamily`.

**Relaciones**: `HAS_PAGE`, `HAS_COMPONENT`, `HAS_TEXT`, `HAS_VARIANT`, `HAS_REQUEST`,
`TRIGGERS`, `DISCOVERED_LINK`, `NAVIGATED_TO {component, action, created_at}`.

**Lo que el crawler scrapea y hoy nadie consume** (materia prima disponible, gratis):

| Dato | Dónde vive | Qué documento lo desbloquea |
|---|---|---|
| `rect` (x, y, width, height) | `Component`, `TextContent` | D7 (objetivos táctiles), D5 (layout) |
| `color`, `background_color`, `font_size`, `font_weight` | `ComponentFacts` | D7 (contraste WCAG) |
| `display`, `position` | `ComponentFacts` | D5 (organismos fijos vs. de flujo) |
| `css_class` | `ComponentFacts` | D5 (ya se usa para clusterizar familias) |
| `required`, `disabled`, `placeholder`, `label`, `name`, `form` | `ComponentFacts` | D7 (prevención de errores), D4 (parámetros) |
| `status`, `failed`, `failure_text` por petición | `Component.network_requests` | D4 (responses), D6 (ramas de error) |
| `body_shape`, `response_shape` | `Request` / `InferredRequest` | D4 (schemas) |
| `metadata` (meta tags) | se extrae en `run_extraction`, **no se persiste** | D1 (contexto del sitio) |
| `created_at` de `NAVIGATED_TO` | relación | D6 (orden de transiciones) |

**Lo que no existe y algún documento necesita**: códigos de estado agregados por endpoint,
jerarquía de contención entre componentes, orden global de interacciones, tiempos de red.

---

## 3. Fases

Criterio de orden: **ninguna fase modifica el crawl principal**. Las fases 2 a 5 leen lo que ya
está en el grafo; la 5.0 agrega un pase de medición *posterior* que no interactúa con nada; la 6
es la primera que agrega escritura nueva durante el crawl (dos propiedades); la 8 es la única
cara.

### Fase 0 — Andamiaje y cobertura

Sin esto, cada documento nuevo engorda `engine.py` y duplica lectura de grafo.

1. **Extraer el aplanado del ledger.** `engine.py:92-97` y `engine.py:132-137` ya son idénticos
   línea por línea, y están a punto de duplicarse cinco veces más. Un
   `flatten_component_ledger(graph_store, site)` en `src/generators/` y ambos lo llaman.
2. **Registro de generadores, en dos etapas.** `Engine.run` hoy cablea D1/D2/D3 a mano; con diez
   documentos eso no escala. Un protocolo `DocumentGenerator` (`generate(graph_store, site) -> str`
   + `extension`) y un `DOCUMENT_REGISTRY`, siguiendo el mismo patrón que `AGENT_REGISTRY` y
   `GRAPH_STORE_REGISTRY` que ya existen. Cada documento se activa por config.

   La segunda etapa es lo que habilita D12: un generador que corre **después** de todos los
   demás y recibe qué se produjo, en vez del grafo. Se alimenta del manifiesto de corrida, que
   `record_run_manifest` ya arma con las rutas de cada archivo — no hace falta un canal nuevo.
3. **D12: el documento maestro.** Los nueve documentos se siguen escribiendo por separado y
   ninguno se borra; al final se escribe uno más que los explica y los referencia. Qué es cada
   documento, para qué sirve, qué encontró en esta corrida (los números que ya tiene el
   manifiesto), y un enlace relativo al archivo completo para el detalle. Es la puerta de entrada
   para alguien que abre `docs/` por primera vez y no sabe cuál de diez archivos leer.
4. **D9: reporte de cobertura, y un encabezado de cobertura en cada documento.** Los datos ya
   están (`count_visited`, `count_unexplored_components`, el manifiesto): páginas terminadas
   sobre totales, componentes explorados sobre descubiertos, rutas que quedaron `Pending`,
   endpoints descubiertos. Esto es lo que convierte "lo más completo posible" en algo honesto:
   un OpenAPI generado sobre un crawl que sólo alcanzó el 40% del sitio lo dice en su propio
   encabezado en vez de aparentar ser el contrato completo.

   El encabezado dice además, siempre y en todos: **esto documenta la superficie pública del
   sitio.** No se crawlea nada detrás de una autenticación (ver H3), así que "100% de cobertura"
   significa 100% de lo alcanzable sin iniciar sesión, no 100% de la aplicación.
5. **Extender `record_run_manifest` y `generate_docs_index`** con las rutas nuevas (hoy sólo
   conocen `prd_path`/`tree_path`/`export_path`).
6. **Escribir la tabla de mapeo de ontología** (sección 1) en `ARCHITECTURE.md`, para que nadie
   vuelva a proponer renombrar `:Component` a `:DOM_Element`.

**Criterio de aceptación**: agregar un documento = un archivo nuevo en `src/generators/` + una
entrada de registro + un flag de config. `engine.py` no crece.

**Coste LLM**: cero.

---

### Fase 1 — Legibilidad del grafo

Va antes que todos los generadores por una razón de dependencia, no de estética: dos de los
cambios de acá son exactamente el dato que las Fases 4 y 6 consumen. Escribir esos generadores
contra el formato actual y migrarlos después es trabajo doble.

**Qué lo hace ilegible hoy, concreto:**

- `Component.interactions` y `Component.network_requests` son **listas de strings JSON**. En el
  browser de Neo4j se ven como `["{\"action\": \"click\", \"resulting_url\": ...}"]`. Es el dato
  más valioso del grafo y es el menos legible de todos.
- Cientos de `:Component` colgando **planos** de cada `:Page` por `HAS_COMPONENT`, sin ningún
  nivel intermedio. Eso es la pelota de pelos.
- El caption por defecto de un `:Component` termina siendo el `path`
  (`div > form > button:nth-of-type(2)`).
- `:TextContent` suma otra pila de hojas al mismo nivel.
- Nada distingue de un vistazo lo que el crawler *vio* de lo que el modelo *dedujo*.

**Qué hacer:**

1. **Promover los blobs JSON a estructura.** `interactions` pasa a
   `(:Component)-[:INTERACTED {action, value, seq, visit_id}]->(:Page)` cuando la interacción
   navegó, y a un nodo `:Interaction` cuando no. Mata dos pájaros: el dato se vuelve legible y
   navegable, y `seq`/`visit_id` son precisamente el orden que la Fase 6 (Gherkin) necesita.
   De `network_requests` se deja de duplicar el blob crudo en la propiedad del Component: el
   nodo `:Request` y la relación `TRIGGERS` ya cubren el caso.
2. **Una propiedad `name` corta en cada nodo, pensada para caption.** Component →
   `botón «Agregar»`; Page → su `title` o `label`, no la URL; Request → `POST /participant_selections`.
   Más un `scripts/neo4j-browser.grass` versionado con captions, colores y tamaños por etiqueta,
   para que abrir el browser sea legible sin configurar nada a mano.
3. **Separar visualmente lo observado de lo inferido.** Una etiqueta extra `:Inferred` en
   `ComponentFamily`, `Molecule`, `Organism` y `BusinessRule`. Es legibilidad y a la vez el
   requisito duro del Human-in-the-Loop: hay que poder ver de un vistazo qué es evidencia y qué
   es deducción.
4. **Un archivo de consultas guardadas** (`docs/consultas-neo4j.md`, más los favoritos del
   browser): "el flujo completo de una ruta", "todos los endpoints que dispara esta página",
   "componentes sin label accesible", "peticiones que fallaron". **Nadie lee un grafo de 5000
   nodos entero; se leen subgrafos.** Esta es la respuesta real a que el grafo no sea un chino —
   el resto son mejoras de presentación sobre esto.
5. **Mitigación de super-nodos**, aplicada donde de verdad va a hacer falta (Fase 3): el
   organismo omnipresente es **un** nodo con `present_on: [urls]`, no una instancia por página.

**Criterio de aceptación**: abrir Neo4j Browser sin configurar nada, correr la consulta guardada
de una ruta, y entender qué pasa en esa pantalla sin leer una sola propiedad JSON serializada.

**Coste LLM**: cero.

---

### Fase 2 — D4: contrato OpenAPI 3.0

**Lee**: `get_inferred_requests(site)`.

**Falta**:

1. `InferredRequest` descarta los códigos de estado. Están en el ledger
   (`network_requests[].status` / `.failed`) pero `build_inferred_requests` no los agrega.
   Agregar `status_codes: Tuple[int, ...]` al contrato y persistirlo en
   `neo4j_request_family_store`. Sin esto la sección `responses:` es una invención.
2. **Unir los shapes de todas las muestras, no quedarse con el primero.** Hoy
   `build_inferred_requests` toma el primer `body_shape` no vacío del grupo. Uniendo las
   muestras y contando en cuántas aparece cada clave se deduce `required` vs. opcional — que es
   justo lo que separa un OpenAPI útil de uno decorativo.
3. `normalized_endpoint` colapsa cada segmento opaco a `{id}`. Eso mapea 1:1 al path templating
   de OpenAPI, pero **dos `{id}` en la misma ruta colisionan** (`/orders/{id}/items/{id}` no es
   válido). Nombrar cada parámetro por el segmento que lo precede: `/orders/{orderId}/items/{itemId}`.
4. Conversión de shape a JSON Schema: la salida de `_json_shape` (`"string"`, `{...}`, `[...]`)
   a `{type: object, properties: {...}}`. Función pura, testeable sin red ni navegador.
5. Deduplicación con `$ref`: shapes idénticos van a `components/schemas/`, nombrados por el
   último segmento no paramétrico del endpoint.
6. `summary`/`operationId` deterministas desde el mapeo CRUD (POST → `create…`, GET con query
   params → `list…`, GET sin ellos → `get…`, PATCH/PUT → `update…`, DELETE → `delete…`).

**Prerrequisito de captura, ver H1 y H2 (sección 6)**: hoy sólo llegan al grafo las peticiones
`xhr`/`fetch` disparadas por una interacción. Quedan afuera las que dispara la carga de una
página y los envíos de formulario clásicos (`document`). Sin resolver eso, D4 documenta un
subconjunto del contrato real y en una app server-rendered puede salir casi vacío. Es la primera
tarea de esta fase, antes que cualquier generación de YAML.

**No-objetivos explícitos**, escritos en el YAML generado: no hay `securitySchemes`, no hay
headers, no hay `example`. El crawler no captura valores reales por diseño.

**Criterio de aceptación**: la salida valida contra el esquema OpenAPI 3.0 en un test
(`openapi-spec-validator`), con un fixture de crawl como entrada.

**Coste LLM**: cero obligatorio. Opcional: una llamada por endpoint para el campo `description`.

---

### Fase 3 — D5: catálogo de componentes (props y variantes)

**Decisión tomada**: el entregable es un catálogo que alimente Storybook, no la pirámide
átomo/molécula/organismo/plantilla. La pirámide se dibuja linda y no alimenta nada; las props y
las variantes son lo que alguien necesita para escribir el componente.

**Consecuencia buena**: esto **no necesita captura nueva**. La pirámide era lo único que exigía
capturar el ancestro landmark en `discover_components.js`. Sin ella, todo sale de datos que ya
están persistidos.

**Lee**: `get_component_families(site)` + `get_component_ledger(site)`.

Por cada familia:

1. **Identidad**: `tag`, `component_type` y el `purpose` ya narrado por
   `narrate_family_purposes`.
2. **Props**, desde `ComponentFacts`, campo por campo: `placeholder`, `label`, `name`,
   `required`, `disabled`, `href`, `input_type`, más `option_labels` para los que tienen
   opciones. Para un control de formulario esto **es** la interfaz del componente.
3. **Variantes**: `common_classes` guarda lo que todos los miembros comparten, así que la
   diferencia entre miembros es el modificador. Un par primario/secundario que sólo difiere en
   la clase de color sale como dos variantes de un componente, no como dos componentes.
4. **Estados observados**: `disabled` y `selected` ya se capturan. `hover` y `focus` no — quedan
   para la Fase 8, y el documento lo dice en vez de fingir que el catálogo está completo.
5. **Dónde se usa**: `member_paths` ya lista un `(page_url, path)` por miembro. La sección
   "aparece en" sale gratis.
6. **Nivel atómico sólo donde es determinable**: por tag (`button`/`input`/`a`/`select`/
   `textarea` → átomo) y por `facts.form` no vacío (pertenece a una molécula de formulario, que
   es el único límite de contenedor hoy capturado). Donde no se puede determinar, se omite el
   campo. No se inventa.

**Fuera de alcance, explícito**: organismos y plantillas. Necesitan capturar el ancestro landmark
(`nav`, `header`, `section`, `table`…) en `discover_components.js` — una línea con precedente
exacto en el mismo archivo (`form: el.closest('form') ? gp(el.closest('form')) : ''`) — pero no
rinden hasta que el catálogo base exista y se vea qué falta. Queda como extensión anotada, no
como deuda. Las plantillas además degradan a la nada en sitios de pocas páginas: agrupar por
firma de organismos con 12 páginas da 12 grupos de uno.

**Salida**: un Markdown por componente más un `components.json` con lo mismo estructurado, para
que un generador de Storybook lo consuma sin parsear prosa.

**Criterio de aceptación**: cada control de formulario del sitio fixture aparece con sus props
reales, verificables contra el HTML. Cero campos inventados — si un dato no está en el grafo, no
está en el documento.

**Coste LLM**: cero obligatorio. Opcional: una llamada por familia para el nombre de dominio,
marcado en el documento como generado y pendiente de revisión humana.

---

### Fase 4 — D6: máquina de estados de flujos

**Lee**: las relaciones `NAVIGATED_TO` e `INTERACTED` (Fase 1) + `get_inferred_requests(site)`.

1. **Los estados son `route_shape`, no URLs crudas.** Sin colapsar, el diagrama de un sitio real
   tiene cientos de nodos y no es documentación de nada. `utils.urls` ya tiene la función.
2. **Etiquetar cada transición con su petición.** Derivable sin captura nueva: si el componente
   X de la página A produjo `resulting_url = B`, y ese mismo componente dispara peticiones, esa
   petición es la de la transición. Persistir el resultado como
   `(:Request)-[:RESULTS_IN_STATE]->(:Page)` — la relación que la investigación pide, ahora con
   un consumidor real que la justifica.
3. **Ramas de error.** `status >= 400` o `failed: true` en la petición de una transición la
   marca como rama de fallo. Esto es lo que hace útil el diagrama (el ejemplo 201 vs. 402 de la
   investigación) y los datos ya están.
4. Salida: `stateDiagram-v2` de Mermaid + una tabla de transiciones con origen, disparador,
   endpoint, estado HTTP y destino.

**Criterio de aceptación**: cada arista del diagrama es trazable a un `NAVIGATED_TO` concreto.
Un test que falle si el generador emite una transición sin fila de respaldo.

**Coste LLM**: cero obligatorio. Opcional: una llamada para nombrar los estados
(`/checkout/{id}` → "Confirmación de pedido").

---

### Fase 5 — La pista de UX/UI: tres documentos, no uno

El UX/UI en una modernización tiene dos trabajos distintos, y meterlos en un solo documento los
arruina a los dos:

- **Diagnóstico** — qué está mal en el sistema viejo, para no reproducirlo (5a, 5c).
- **Especificación** — cómo se ve el sistema viejo, para poder reconstruirlo (5b).

Los tres salen de datos que el crawler **ya captura**: `color`, `background_color`, `font_size`,
`font_weight`, `display`, `position`, `rect`, `label`, `required`, `disabled`. El comentario de
`discover_components.js` que dice que esas propiedades están ahí "para un futuro pase de
reconstrucción visual" describe exactamente 5b — la materia prima está esperando desde entonces.

**Regla transversal de la pista**: cada hallazgo es prescriptivo, no descriptivo. No "el botón
no tiene label", sino "el botón no tiene label → en la reconstrucción, `aria-label` obligatorio
en controles sin texto visible". El objetivo del proyecto es refactorizar la experiencia, no
traducirla 1:1; un documento que sólo describe el pasado no sirve para eso.

#### 5.0 — El pase de medición (prerrequisito de 5b y 5c)

El navegador del crawl está afinado para velocidad, no para representar lo que ve un usuario
([crawl4ai_crawler.py:186](src/crawlers/crawl4ai_crawler.py:186)): viewport 800×600,
`light_mode`, `memory_saving_mode`, y `block_images` descartando `image`/`media`/`font`. Todo
`rect` del grafo está medido a 800×600, sin webfonts y sin imágenes de fondo.

**Decisión tomada**: no se toca el crawl principal. Se agrega un **pase de medición posterior**,
que corre cuando el crawl ya terminó y el grafo está completo.

Qué es y qué no es:

- **Sólo navega y mide.** Visita páginas ya visitadas con `block_images` desactivado y viewport
  realista (1280×800, y opcionalmente 375×812 para móvil), re-lee estilos computados y
  geometría, saca un screenshot, y actualiza esos campos en los nodos que ya existen.
- **No interactúa con nada.** No hace clic, no llena campos, no toca la frontera de interacción
  ni descubre páginas nuevas. Por eso es barato: el crawl principal gasta su tiempo en las
  interacciones, no en las navegaciones.
- **No descubre lo que faltó.** Re-mide lo que ya está, bajo condiciones representativas. Lo que
  el crawl no alcanzó sigue sin estar — eso lo reporta D9, no este pase.
- **Alcance por muestra**: una página por `route_shape`, no todas. Las instancias de una misma
  ruta comparten layout; medir las 40 páginas de detalle de producto da el mismo resultado que
  medir una.

**Qué depende de esto y qué no**, con precisión: las comparaciones **relativas** sobreviven sin
el pase (si todos los colores se miden igual de mal, "estos tres botones tienen fondos
distintos" sigue siendo cierto), así que **5a funciona igual**. Los **umbrales absolutos** no:
ratio de contraste 4.5:1, objetivo táctil de 44 px y el sistema de espaciado necesitan medidas
reales. Por eso 5b y 5c cuelgan de esto y 5a no.

**Coste**: una navegación por `route_shape`, sin interacciones. Es una fracción del crawl
original, no su duplicación.

#### 5a — D7: auditoría de usabilidad (Nielsen)

Cada hallazgo es una fila con regla, evidencia (`page_url` + `path`), severidad y recomendación.

| Regla | Dato que la evalúa | Heurística de Nielsen |
|---|---|---|
| **Componentes de la misma familia con estilo distinto** | `ComponentFamily` + `color`/`background_color` de sus miembros | Consistencia y estándares |
| **Misma acción, distinto nombre** ("Guardar" / "Confirmar" / "Aceptar" para el mismo endpoint) | `text` de los componentes agrupados por `Request` | Consistencia y estándares |
| Campo sin `type` semántico (el `name`/`placeholder` dice email/tel/fecha, `input_type` dice `text`) | `input_type`, `name`, `placeholder` | Prevención de errores |
| Campo sin `required` en un formulario cuyo submit devolvió 4xx | `facts.required`, `facts.form`, `status` | Prevención de errores |
| Control `disabled` sin texto cercano que lo explique | `facts.disabled` + `TextContent` por proximidad de `rect` | Ayuda y documentación |
| Petición que falló sin cambio de texto en pantalla | `failed` + `TextContent` | Visibilidad del estado del sistema |
| **Ruta sin salida** (estado del FSM sin transiciones salientes) | FSM de la Fase 4 | Control y libertad del usuario |
| **Tarea larga** (cantidad de pasos del camino más corto hasta un endpoint de negocio) | FSM de la Fase 4 | Flexibilidad y eficiencia |

Las dos primeras filas son las que valen más, y **sólo son computables porque existe el
clustering de familias**: tres colores distintos de botón primario es una inconsistencia que
nadie detecta a ojo en una app grande, y acá sale de una consulta. Las dos últimas se leen del
FSM de la Fase 4, no de componentes sueltos — por eso esta fase va después.

#### 5b — D10: especificación visual y design tokens

El documento que alimenta la reconstrucción. Todo determinista, cero captura nueva.

1. **Paleta**: agrupar `color`/`background_color` de todos los componentes por frecuencia. La
   heurística que decide si esto sirve o es basura: **colapsar colores perceptualmente cercanos**
   (distancia CIEDE2000 bajo un umbral) antes de contar. Sin eso el documento lista 47 grises
   casi iguales en vez de una paleta.
2. **Escala tipográfica**: los pares `(font_size, font_weight)` distintos, ordenados por tamaño y
   anotados con su frecuencia. De paso queda medida la salud de la escala: seis niveles es un
   sistema, veintitrés es deuda.
3. **Espaciado**: distancias entre `rect` de elementos hermanos, redondeadas a la grilla más
   probable (4 px u 8 px). Detecta si el sitio tiene sistema de espaciado o valores al azar.
4. **Variantes por familia**: para cada `ComponentFamily`, en qué se diferencian sus miembros.
   `common_classes` ya guarda lo que *comparten*, así que la diferencia entre miembros **es** el
   modificador — primario vs. secundario vs. destructivo, sin tener que adivinarlo.
5. Salida doble: un `design-tokens.json` consumible por Tailwind o Storybook, y un Markdown
   legible por una persona. Es el insumo que la investigación pide para el catálogo de
   componentes aislados.

#### 5c — D11: auditoría de accesibilidad (axe-core, WCAG 2.1 AA)

Separada de Nielsen a propósito: tiene un estándar nombrado, criterios numerados y otra
audiencia. **Decisión tomada: el motor es axe-core, no reglas propias.**

**Por qué no reglas propias.** La versión anterior de esta fase calculaba contraste desde
`ComponentFacts.background_color`, que sale de `getComputedStyle().backgroundColor` — y eso
devuelve `rgba(0,0,0,0)` para cualquier elemento cuyo fondo lo pinta un ancestro, que son casi
todos. Habría dado resultados mal a escala. axe resuelve apilado de fondos, opacidad y texto
sobre gradiente, con ~90 reglas mantenidas por Deque contra las siete escritas a mano.

**Cómo se integra, concretamente:**

1. **`axe.min.js` vendorizado en `src/crawlers/js/`**, como sexto asset junto a
   `discover_components.js` y compañía, cargado con el mismo `_load_js()` de
   [page_extraction.py](src/crawlers/page_extraction.py). **No** se usa `@axe-core/playwright`:
   es un paquete npm y en este proyecto no hay Node en ningún lado (`requirements.txt` es Python
   puro, Docker sólo levanta Neo4j). Cero dependencias Python nuevas.
2. **Corre dentro del pase de medición (5.0)**, no durante el crawl principal. Es el encaje
   natural: 5.0 ya navega con un browser real, con imágenes desbloqueadas y viewport realista —
   que es exactamente lo que el chequeo de contraste necesita para no mentir. Corriendo durante
   el crawl daría resultados sesgados y lo frenaría.
3. **Scope explícito**: `runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}`.
   Sin eso entran las reglas de best-practice de axe y el documento se llena de ruido que no es
   WCAG.
4. **El punto de integración que decide si esto sirve**: axe devuelve `nodes[].target` con
   selectores CSS **propios**, no los paths de `gp()`. Hay que resolver cada `target` a su
   elemento y recalcular nuestro path en el mismo `page.evaluate()`, para que cada violación
   enganche con el `:Component` que ya existe. Sin ese paso, D11 es un JSON al costado del grafo
   en lugar de una capa sobre él.
5. **Forma en el grafo**: un nodo `(:A11yViolation:Inferred {rule_id, impact, wcag_criteria,
   help_url})` por **regla**, no por instancia, con una arista `VIOLATES` desde cada componente
   infractor. Así "cuántos componentes rompen la regla X" es una consulta, y no se crean miles
   de nodos casi idénticos. Es un super-nodo por diseño, pero de sólo lectura y siempre
   consultado por regla — el caso aceptable.

**Lo que axe no cubre y queda como complemento propio**, verificado, no asumido:

- **Objetivo táctil < 44×44 px** (WCAG 2.2, criterio 2.5.8): la regla `target-size` de axe no
  está en el conjunto estable. Se queda como regla nuestra sobre `rect`, que ya está persistido.
- Todo lo que depende de datos de red o interacción — "petición que falló sin cambio de texto en
  pantalla" — no es cosa de axe y vive en 5a, que es donde corresponde.

**Lo que espera a la Fase 8**: foco visible (2.4.7), orden de tabulación (2.4.3) y navegación por
teclado (2.1.1). axe tiene reglas para eso pero necesitan recorrer la página con `Tab`, que hoy
no se hace.

**Dos consideraciones de vendorizar un archivo de terceros**, que conviene resolver de entrada:
la **versión de axe-core queda anotada** en el encabezado del archivo y en el manifiesto de la
corrida (un hallazgo cambia si cambia el motor, y hay que poder explicar por qué); y **axe-core
es MPL-2.0**, copyleft a nivel de archivo — commitear el `.js` sin modificar no afecta la licencia
del resto del código, pero es una dependencia de tercero entrando al repo y merece quedar escrito.

**Techo honesto**: el testing automatizado de accesibilidad detecta del orden del 30-40% de los
problemas WCAG reales (axe publica hasta ~57% incluyendo sus reglas de best-practice). D11 no
queda completo con esto: queda **creíble**, que es distinto y mejor que siete reglas caseras.

**Criterio de aceptación de las tres**: cero hallazgos sin `(page_url, path)` de evidencia — para
D11 eso significa que toda violación de axe resolvió a un `:Component` existente, y las que no
resuelvan se reportan aparte en vez de descartarse en silencio. Cada regla **propia** (5a, y el
target-size de 5c) con su test unitario sobre un componente fabricado; las reglas de axe no se
re-testean, se confía en el motor. El `design-tokens.json` parsea.

**Coste**: un asset de ~600 KB, unos cientos de milisegundos por página, y sólo sobre la muestra
del pase de medición. Despreciable. **Coste LLM**: cero en las tres. Opcional: una llamada por
grupo de hallazgos para redactar la recomendación de refactor en prosa.

---

### Fase 6 — D8: Gherkin sobre trazas ordenadas

Es la primera fase que toca el crawler.

**El problema**: un escenario Gherkin es una *secuencia*. El grafo guarda hechos por componente,
no trazas.

**Captura nueva mínima**: un `visit_id` por pasada de página y un `step_seq` monotónico, escritos
en `record_component_interaction` y en `record_edge`. `GraphStoreSink` es el único punto de
escritura, así que el cambio queda localizado ahí y en `PageVisitor`. Son las mismas dos
propiedades que la Fase 1 ya pone en la relación `INTERACTED`: acá se llenan de verdad.

**Con eso alcanza**, porque `MechanicalCrawler` ya corta la pasada cuando una interacción navega:
ese corte *es* el final natural de un escenario. Una traza = las interacciones de un `visit_id`
ordenadas por `step_seq`.

**Construcción del escenario**, todo determinista:

- `Given` — la página de origen (título + ruta) y el estado previo relevante (valor actual de un
  stepper, opción seleccionada de un choice group).
- `When` — un paso por interacción de la traza, con el texto visible del control, no su selector.
- `Then` — las peticiones emitidas con su método, endpoint y estado HTTP, más la URL resultante.

**El LLM sólo nombra, nunca inventa pasos**: una llamada por escenario para el `Feature:` y el
título en lenguaje de negocio. Los pasos se renderizan desde el grafo.

**Escenarios multi-página** (login → carrito → checkout) se encadenan **sobre el FSM de la Fase
4**, no sobre trazas crudas: recorrer el diagrama de estados y unir las trazas de cada tramo.
Por eso la Fase 4 va antes.

**Diagramas de secuencia UML (H4), de yapa.** La investigación pide FSM **y** diagramas de
secuencia; la Fase 4 cubre el primero. El segundo es el mismo dato de esta fase renderizado de
otra forma: una traza ordenada *es* un diagrama de secuencia (actor → control de UI → endpoint →
respuesta, en el tiempo). Se emite como `sequenceDiagram` de Mermaid junto a cada escenario, sin
ninguna consulta ni captura adicional. Determinista, cero LLM.

**Criterio de aceptación**: un test que falle si algún `When`/`Then` generado no tiene fila de
grafo detrás. El `.feature` parsea con un parser de Gherkin real.

**Coste LLM**: una llamada por escenario, sólo para títulos.

---

### Fase 7 — `:BusinessRule` — **congelada**

**Decidido: el HITL queda fuera de alcance por ahora** (H6). El foco es generar documentos y
capturar información, no montar un ciclo de revisión y aprobación.

**Recomendación objetiva: congelar la fase entera, no hacerla a medias.** El valor de
`:BusinessRule` era casi todo el HITL — poder navegar desde una regla inferida hasta la petición
y el componente que la originaron, y aprobarla o rechazarla. Sin esa parte, lo que queda es
prosa generada por el modelo sobre lo que hace el sistema, que es sustancialmente **lo mismo que
D1 ya produce**. Hacerla igual sería agregar un décimo documento que repite el primero.

Cuando el HITL entre en alcance, esta fase se descongela tal cual está descrita acá:
`(:BusinessRule:Inferred {description, confidence})` con `<-[:IMPLEMENTS]-(:Request)` y
`-[:EVIDENCED_BY]->(:Component)`, más el estado de revisión que hoy falta. Prerrequisitos reales:
Fases 4 y 6 — una regla sin traza que la respalde no es auditable, es una frase.

---

### Fase 8 — Señales UX que sí requieren captura nueva (go/no-go aparte)

Separada a propósito: es la única parte cara del plan y no bloquea nada de lo anterior.

- ~~Latencia por petición~~ — **movida a la Fase 2**: el `timestamp` ya viene en cada evento
  capturado por crawl4ai (ver H8), así que no pertenece a la fase cara.
- **Mensajes de error tras un submit fallido**: `record_text_content` corre una vez por visita,
  no por interacción. Necesitaría re-extraer texto después de cada interacción con status 4xx.
  Coste medio, valor alto — es el candidato de esta fase que más rinde.
- **Estados visuales `hover` y `focus`**: hoy sólo se capturan los estilos en reposo. Un pase que
  aplique `:hover`/`:focus` por CSS y re-lea los estilos completaría D10 con los estados que un
  sistema de componentes necesita sí o sí. Coste medio, y es lo que separa un design-token
  "colores y tipografías" de una especificación de componente usable.
- **Foco visible, orden de tabulación y navegación por teclado** (WCAG 2.4.7, 2.4.3, 2.1.1):
  requiere recorrer la página con `Tab` durante el crawl. Completa D11 con los criterios que hoy
  quedan afuera.
- **Presencia de indicador de carga durante la espera**: requiere un snapshot del DOM *durante*
  la petición, no antes ni después. Es un cambio profundo en el ciclo de interacción del
  crawler. Mi recomendación es no hacerlo salvo que la auditoría de UX se vuelva un entregable
  de primera línea.

---

## 4. Techos de completitud (qué no va a poder tener cada documento)

Esto no es pesimismo: es lo que hay que saber para no descubrirlo con el documento entregado.

| Documento | Techo | Se puede subir? |
|---|---|---|
| D4 OpenAPI | Sin `securitySchemes`, headers ni ejemplos — el crawler guarda shapes, no valores | No sin romper la decisión de privacidad |
| D4 OpenAPI | Sólo los endpoints que el crawl **disparó de verdad** | Sí: más cobertura de crawl |
| D5 catálogo | Sin organismos ni plantillas: fuera de alcance por decisión, no por imposibilidad | Sí: capturar el ancestro landmark (1 línea de JS) |
| D5 catálogo | Los nombres de dominio ("tarjeta de producto") los pone el LLM, son aproximados | Parcialmente: revisión humana |
| D5 catálogo | Estados `hover`/`focus`/`active` ausentes — un catálogo de componentes sin ellos está incompleto para Storybook | Sí: Fase 8 |
| D6 FSM | Sólo los estados que el crawl alcanzó; flujos detrás de login dependen de `login_helper.py` | Sí: credenciales y más cobertura |
| D7 Nielsen | 8 reglas deterministas en 5a; estado del sistema y mensajes de error esperan a la Fase 8 | Sí: Fase 8 |
| D10 Design tokens | Sólo estilos en reposo — `hover`/`focus`/`active` no se capturan | Sí: Fase 8 |
| D10 Design tokens | Es la paleta que el sitio **usa**, no la que su diseño *pretendía*: si el legacy es inconsistente, los tokens salen inconsistentes | No, y está bien — la inconsistencia es el hallazgo |
| D11 WCAG | axe detecta del orden del 30-40% de los problemas WCAG reales; foco, tabulación y teclado esperan a la Fase 8 | Parcialmente: Fase 8 |
| D11 WCAG | Nunca va a ser una certificación: los criterios que exigen juicio humano (lenguaje claro, orden lógico) no se automatizan | No |
| D11 WCAG | Los hallazgos dependen de la versión de axe-core vendorizada | No, pero queda anotada en el manifiesto |
| D8 Gherkin | Escenarios de "lo que se puede hacer", no "lo que un usuario hace" — el crawl es exhaustivo, no orientado a objetivos | Parcialmente: encadenado sobre el FSM |

**El techo dominante no está en los generadores, está en la cobertura del crawl.** Si el crawl
no pasa del login o nunca logra enviar un formulario, ningún generador puede inventar el
endpoint. Por eso D9 (reporte de cobertura) es Fase 0 y no un adorno: es la métrica que dice
cuán completo es todo lo demás, y la que señala dónde invertir para subir el techo.

---

## 5. Resumen de dependencias

```
Fase 0 (andamiaje + D9 cobertura)
  └── Fase 1  Legibilidad del grafo
        ├── Fase 2  OpenAPI                      ── lee el grafo
        ├── Fase 3  D5 catálogo de componentes   ── lee el grafo
        ├── Fase 4  FSM                          ── lee el grafo
        │     ├── 5a  D7 usabilidad (Nielsen)    ── lee el grafo
        │     └── Fase 6  Gherkin + secuencia    ── escritura nueva: visit_id + step_seq
        └── 5.0  Pase de medición                ── navegación posterior, sin interacción
              ├── 5b  D10 design tokens          ── + Fase 3 (variantes por familia)
              └── 5c  D11 accesibilidad (axe)
                    └── Fase 8  UX con captura nueva (go/no-go)

  (D12, documento maestro: última etapa, después de todo lo que se haya generado)
  (Fase 7, BusinessRule: congelada — vuelve si el HITL entra en alcance)
```

5a cuelga de la Fase 4 porque dos de sus reglas (rutas sin salida, largo de tarea) se leen del
FSM; sus reglas de consistencia son comparaciones relativas y no necesitan el pase de medición.
5b y 5c sí lo necesitan: trabajan con umbrales absolutos. 5c es la rama más barata y corta de
todo el plan si hace falta un resultado rápido y demostrable.

## 6. Huecos detectados al contrastar el plan con la investigación

Tres son defectos de captura en el código, no del plan. Los otros seis son cosas que la
investigación pide y el plan no cubría.

### En el código (afectan el techo de varios documentos)

**H1 (resuelto en la Fase 2). Las peticiones que dispara la carga de una página no se capturaban.**
`capture_network_requests=True` está puesto sólo en `Crawl4AICrawler._interact()`, nunca en
`discover_page()`. Está documentado y el razonamiento es correcto *para su propósito original*:
"las peticiones de una carga de página no son atribuibles a la interacción de un componente"
([crawl4ai_crawler.md#_interact-network-capture](docs/dev/crawlers/crawl4ai_crawler.md)). Pero
ese razonamiento no aplica a D4: **un endpoint no necesita componente disparador para ser parte
del contrato de la API.** Una SPA que carga sus datos al entrar a la ruta pierde todos esos
endpoints, y hoy nada lo reporta. Requiere decisión nueva: capturar también en `discover_page()`
y marcar esas peticiones como `triggered_by: page_load` en vez de por componente.

**H2 (resuelto en la Fase 2). Los envíos de formulario clásicos se descartaban.**
`_MEANINGFUL_RESOURCE_TYPES = {"xhr", "fetch"}` deja afuera `document`, y un form POST que navega
la página **es** de tipo `document`. Una app legacy renderizada en el servidor —el caso de uso
central de este proyecto— hace exactamente eso. D4 saldría casi vacío en ese escenario y D9 no
lo señalaría, porque cuenta páginas y componentes, no tipos de petición. Requiere decisión:
admitir `document` cuando el método no es GET, que es la señal barata de "esto es un envío de
datos, no una navegación".

**H3. `login_helper` está huérfano.**
[login_helper.py](src/core/login_helper.py) guarda el `storage_state` y te dice que uses
`--storage-state` o `storage_state_path:` en `pragma.yaml`, pero **nada en `src/` lee ninguno de
los dos**, y `cli.py` no tiene subcomando `login`. Verificado por búsqueda directa: `storage_state`
sólo aparece dentro de ese archivo.

**Decidido: no se cablea el login por ahora. Todo el alcance es la superficie pública.** Eso
queda escrito en el encabezado de cobertura de cada documento (Fase 0, punto 4), para que
"100% de cobertura" nunca se lea como "100% de la aplicación".

Consecuencia aparte, de higiene: el módulo queda como código muerto que **imprime instrucciones
para flags que no existen**, lo cual es peor que no estar — alguien lo va a correr y va a creer
que funcionó. O se borra, o se marca explícitamente como no cableado. No es parte de este plan,
pero conviene resolverlo antes de que alguien lo use.

### Del plan (la investigación lo pide, el plan no lo cubría)

**H4. Diagramas de secuencia UML.** La investigación pide FSM **y** diagramas de secuencia; sólo
planifiqué el FSM. **Resuelto: agregado a la Fase 6** — una traza ordenada *es* un diagrama de
secuencia, se emite como `sequenceDiagram` de Mermaid junto a cada escenario, sin captura ni
consulta adicional.

**H5. Cómo se relacionan los documentos entre sí.** La investigación pide que los hallazgos de UX
se integren *dentro* del PRD. El plan producía archivos independientes sin referencias cruzadas.

**Decidido: las dos cosas.** Cada documento se sigue generando por separado y ninguno se borra;
al final se escribe **D12**, que los explica y los referencia (Fase 0, punto 3). Quien quiere el
panorama lee uno solo; quien quiere el detalle sigue el enlace.

**H6. El HITL es trazabilidad, no gobernanza.** La investigación describe un ingeniero que revisa
y **autoriza** antes de la síntesis de código.

**Decidido: HITL fuera de alcance por ahora.** El foco es generar los documentos y capturar toda
la información posible. Sin la parte de gobernanza, la Fase 7 pierde casi todo su sentido — ver
esa fase para la recomendación.

**H7. WebSockets.** **Decidido: fuera de alcance.** Queda anotado que si la aplicación tiene
funcionalidad en tiempo real, no va a aparecer en ningún documento.

**H8. La latencia de las peticiones. Se puede, y es gratis.**

Verificado en el paquete instalado: **cada evento capturado por crawl4ai ya trae `timestamp`**
(`async_crawler_strategy.py:642` para `request`, `:667` para `response`). La latencia es la resta
entre los dos, y ambos ya están en `raw_events` —`filter_meaningful_requests` simplemente no los
lee. Son unas pocas líneas: el mismo patrón de mapa-por-URL que esa función ya usa para
`statuses_by_url`.

**Decidido: se hace, y sube de la Fase 8 a la Fase 2**, junto con el resto de los arreglos de
`network_filter`.

Dos salvedades honestas. La primera: la latencia medida es la del navegador del crawl, con
`light_mode` y recursos bloqueados — sirve como señal **relativa** ("este endpoint tarda diez
veces más que aquel") y para la regla de Nielsen de visibilidad del estado del sistema, no como
número de rendimiento absoluto. La segunda: los mapas de `filter_meaningful_requests` se indexan
por URL, así que dos peticiones a la misma URL dentro de un mismo lote se pisan. Es una
limitación que ya existe para `status`, no una que introduzca la latencia.

**H9. APOC no está instalado.** `docker-compose.yml` usa `neo4j:5.24-community` pelado, sin
plugins. La investigación da `apoc.meta.data` por disponible. Sólo importa si algún día se hace
text-to-Cypher o Q&A sobre el grafo — que sigue fuera de alcance según
`research/rag-over-neo4j-for-future-qa.md`, pero nunca lo confirmamos explícitamente.

## 7. Decisiones

### Tomadas

1. **El crawl principal no se toca.** Las medidas sesgadas por el browser afinado se corrigen en
   un pase de medición posterior, sólo navegación, por muestra de `route_shape` (5.0).
2. **D5 es un catálogo de props y variantes, no la pirámide de Atomic Design.** Organismos y
   plantillas quedan fuera de alcance; como consecuencia, la captura del ancestro landmark no
   hace falta y la Fase 3 no toca el crawler.
3. **La accesibilidad la mide axe-core vendorizado**, corriendo dentro del pase de medición, no
   siete reglas propias. Sobrevive como regla nuestra sólo el objetivo táctil (`rect`).
4. **Sin login (H3).** El alcance es la superficie pública, y cada documento lo dice en su
   encabezado de cobertura.
5. **Documentos por separado *y* un documento maestro (H5).** D12 se escribe al final,
   referenciando a los demás sin reemplazarlos.
6. **HITL fuera de alcance (H6)**, y en consecuencia la Fase 7 queda congelada entera en vez de
   hacerse a medias.
7. **WebSockets fuera de alcance (H7).**
8. **La latencia se captura (H8)**, y sube de la Fase 8 a la Fase 2: el dato ya viene en los
   eventos de crawl4ai.

9. **Los artefactos derivados se persisten** en Neo4j, marcados con la etiqueta `:Inferred`.
   Cuesta nada hoy y evita retrofitearlo en cuatro rutas de escritura el día que el HITL entre.
10. **Se mantienen los nombres de la ontología actual**, con el mapeo documentado en
    `ARCHITECTURE.md`.
11. **La migración de `interactions` es una ruptura, sin script de migración.**
    `PragmaConfig.fresh` ya viene en `true` y purga el sitio antes de cada crawl, así que una
    corrida normal no se entera. Un grafo con `fresh: false` necesita re-crawlearse.

### Abiertas

Ninguna bloquea la Fase 2.
