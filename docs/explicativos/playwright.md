# Cómo funciona el scraper de Playwright

> Código de referencia: [`src/scrapers/playwright_scraper.py`](../../src/scrapers/playwright_scraper.py)
> (`PlaywrightScraper`, "las manos" del sistema — implementa la interfaz `Scraper` de
> [`src/core/interfaces.py`](../../src/core/interfaces.py)).

## Ciclo de vida del browser

El browser (Chromium) se lanza perezosamente (`_ensure_browser`) recién en la primera llamada
real, y se mantiene vivo durante todo el run — una sola pestaña (`self._page`), no una por
navegación. `headless` y `wait_seconds` (segundos extra para dejar asentar la página después de
navegar/clickear, antes de leer componentes/links — subilo en sitios lentos o muy cargados de JS)
se configuran al crear el scraper.

## Las acciones: `navigate`, `click`, `fill`, `submit`

Las cuatro devuelven un `PageState` fresco (recalculado con `get_state()` después de la acción).
Contrato compartido: **una falla real (selector inválido, elemento no clickeable, timeout) se
propaga como excepción** — no se traga silenciosamente. Solo la espera de `networkidle` posterior
a la acción es "best effort" (muchos sitios con polling/analytics nunca llegan a estar realmente
idle, así que no vale la pena fallar el run por eso).

- **`click`/`fill`**: si el elemento existe en el DOM pero no es visible (típico de un submenú que
  solo se renderiza al hacer hover del padre, aunque esté presente todo el tiempo), se reintenta
  con `force=True`, que saltea las verificaciones de visibilidad/actionability de Playwright y
  despacha el evento directo.
- **`submit`**: aprieta Enter sobre el selector (pensado para usarse justo después de un `fill`
  sobre el mismo elemento) — cubre el patrón común de un solo campo de búsqueda/login sin
  necesitar un botón de submit separado.
- **`frame_url`** (parámetro opcional en las tres): si el componente fue descubierto dentro de un
  `<iframe>`, esto apunta la acción al documento de ese frame en vez del documento principal — ver
  más abajo.

## Qué extrae `get_state()`

- **`title`**, **`metadata`** (meta tags).
- **`description`**: un resumen corto (~300 caracteres) de qué trata la página —
  `<meta name="description">` si existe, si no el primer `<h1>` + el primer párrafo sustancial
  (>20 caracteres, para saltear badges/labels cortos). Sin ningún NLP — mismo principio que el
  resto del proyecto de preferir señales deterministas por sobre heurísticas de IA cuando el dato
  ya está disponible mecánicamente.
- **`components`**: la lista de elementos interactivos — el corazón de este documento, ver abajo.
- **`links`**: todos los `<a href>` de la página (de cualquier esquema, no solo http/https — un
  `scheme` en cada uno le permite a `SimplePRDGenerator` decidir explícitamente qué hacer con un
  `mailto:`/`tel:`/`javascript:`, sin descartarlo en silencio antes de que el llamador se entere
  de que existía).

## Descubrimiento de componentes: dos capas

`_discover_components()` corre en **cada frame de la página** (no solo el documento principal —
ver "Iframes" abajo), y busca en dos capas, en orden de preferencia:

1. **Capa `semantic`**: tags nativos (`button`, `a`, `input`, `select`, `textarea`) más los roles
   ARIA que las librerías de componentes modernas (Radix, shadcn/ui, MUI, Headless UI...) usan
   para construir widgets no nativos — `role="option"`, `"menuitem"`, `"tab"`, `"checkbox"`,
   `"radio"`, `"switch"`, `"combobox"`, etc. Sin esto, un popover con opciones armadas como
   `<div role="option">` (sin ser un `<select>` real) queda completamente invisible para el
   descubrimiento.
2. **Capa `pointer`**: un catch-all para el caso que queda — un elemento con `cursor: pointer`
   pero sin tag semántico ni rol ARIA (un `<div onClick=...>` sin ninguna marca de accesibilidad;
   mala práctica, pero real). Se excluye cualquier elemento que ya esté cubierto por la capa
   semántica (en cualquier dirección: un `<div>` con cursor pointer que envuelve un `<button>` real
   es redundante con ese botón), y se limita a 100 elementos — es un complemento, no el camino
   principal de descubrimiento.

Cada componente lleva su propio `discovery_layer` (`"semantic"` o `"pointer"`), que
`SimplePRDGenerator`/`GraphStore` usan para excluir la capa más ruidosa de ciertos conteos (ver
`semantic_only` en [`neo4j.md`](neo4j.md)).

## Shadow DOM e iframes

Dos gaps que existían en versiones anteriores del scraper y ya están resueltos:

- **Shadow DOM abierto**: `collectRoots` recorre recursivamente el `.shadowRoot` de cada elemento
  y corre la búsqueda de componentes también dentro de cada shadow root encontrado, no solo en
  `document`. Un shadow root cerrado (`mode: 'closed'`) se saltea automáticamente, porque
  `.shadowRoot` da `null` en ese caso — no hace falta detectarlo aparte.
- **Iframes**: `_discover_components`/`_extract_links` corren en **todos los frames de la
  página** (`self._page.frames`), no solo el documento principal. Cada componente encontrado
  dentro de un iframe lleva su propio `frame_url` (vacío para el documento principal), que
  `click`/`fill`/`submit` usan para resolver el frame correcto vía `_resolve_frame` antes de
  actuar — si el frame ya no existe (se removió o cambió de `src`), falla con un error explícito
  en vez de actuar sobre el documento equivocado en silencio.

## Construcción del selector (`path`)

Cada componente lleva un `path` — un selector CSS único y estable dentro de esa carga de página:
`tag#id` si el elemento tiene id (escapado con `CSS.escape`, porque algunas librerías generan ids
con `:` como `radix-:r0:`, que rompe un selector CSS si no se escapa), o `tag:nth-of-type(n)`
entre sus hermanos del mismo tag si no. El recorrido hacia la raíz (`gp`) también cruza el límite
de un shadow root vía `getRootNode().host`, así un elemento adentro de un shadow DOM igual obtiene
un path resoluble.

## Sesión persistente / login (`storage_state`)

Cada corrida de Pragma lanza un Chromium **nuevo y vacío** (`chromium.launch()`), completamente
aislado de cualquier browser que tengas abierto vos — loguearte a mano en tu Chrome de siempre no
tiene ningún efecto sobre la sesión de Pragma, son procesos totalmente distintos sin cookies
compartidas.

Para crawlear un sitio que requiere login, `PlaywrightScraper` acepta un `storage_state_path`
opcional (`None` por default — cero cambio de comportamiento si no lo usás). Si está configurado y
el archivo existe, se carga al crear el contexto del browser (`browser.new_context(storage_state=...)`),
así la corrida arranca ya autenticada. Si el archivo no existe todavía (nunca corriste el paso de
login), no rompe la corrida — cae a una sesión nueva y desconectada, con una advertencia impresa
(`_browser_context_kwargs`).

Cómo generarlo: `python3 src/cli.py login <url>` (`src/core/login_helper.py`) abre un Chromium
**visible**, te deja loguearte a mano, y al apretar Enter en la terminal guarda cookies +
localStorage a un archivo JSON (`storage_state.json` por default). Ese archivo tiene sesiones
reales — está en `.gitignore` a propósito, nunca se debe commitear.

`close()` deliberadamente **no** re-guarda el estado al final de la corrida — si una cookie se
renovó durante el crawl, el archivo no se actualiza solo; hay que volver a correr `login` si la
sesión guardada expira.

## Qué más lleva cada componente

Más allá de `tag`/`text`/`path`, cada componente incluye lo necesario para que el modelo decida
sin ver el HTML crudo: `input_type`, `placeholder`, `label` (de un `<label for="...">` asociado, un
`<label>` envolvente, o `aria-labelledby` — cubre el caso común de un campo con label real pero
sin placeholder), `name`, `role`, `disabled`, `value`/`required` (solo en input/textarea/select),
`visible`, `rect` (bounding box en píxeles relativos al viewport, al momento del descubrimiento),
`selected` (si es la opción activa dentro de su grupo — radio/checkbox/tab/listbox), y `form` (el
path del `<form>` más cercano, para que el aviso de "te falta completar este formulario" se
agrupe por formulario y no por página entera).

El texto accesible de un componente (`text`) sigue una cadena de fallbacks deliberada
(`getAccessibleLabel`) antes de caer a `textContent` crudo: `aria-label` → `aria-labelledby` →
`title` → `alt` de una `<img>` hija → `<title>` de un `<svg>` hijo. Sin esto, un ícono con solo una
imagen con `alt` (sin `aria-label` propio) se documentaba como "Unnamed Element" a pesar de tener
un nombre accesible real, a una sola línea de distancia.
