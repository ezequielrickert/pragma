# Diagnóstico: la corrida de 12 horas que nunca terminó

> Escrito el 2026-08-14 contra `main` en `ec03ea8` (PR #38).
> **Revisado el mismo día contra `main` en `2c4e2f3`** (PR #39 y #40 de Ezequiel).
> Pregunta que lo motiva: *"corrí una URL con demasiadas pantallas, estuvo 12 h y nunca
> terminó; algo hace que se pase de las 40 iteraciones del yaml"*.

## Respuesta corta

**Las 40 iteraciones nunca existieron.** `max_iterations` no es una opción de este
programa: no aparece en ningún `.py` del repo, sólo en tu `pragma.yaml`. El cargador de
config descarta en silencio toda clave que no sea un campo del dataclass, así que esa
línea nunca hizo nada.

El límite real se llama `max_pages`, y su default es `None` — **crawl ilimitado**.

## Estado después del PR #40 (`2c4e2f3`): peor, no mejor

Verificado causa por causa contra el merge:

| Causa | Estado |
|---|---|
| §1 `max_iterations` clave muerta | **igual** — cero referencias en `.py` |
| §2 `max_pages` = `None` | **igual** — `core/config.py:46` |
| §3 el YAML no se lee | **igual** — `config.py:111` vs `wizard.py:16` |
| §4 re-encolado sin tope | **igual** — `loop.py` sin cambios |
| §5 techo por página | **eliminado** — era el último backstop numérico |

Ninguna de las cuatro causas originales se tocó, y el PR #40 borró el único límite que
quedaba (§5). El propio mensaje del commit `d59ce99` lo dice sin vueltas:

> *"a page whose DOM regenerates genuinely new content forever
> (infinite-scroll/live-chat-style) now hangs the crawl indefinitely rather than
> finishing with a partial view — there is no other backstop left."*

Es una decisión consciente y argumentada (prioriza un grafo completo sobre un peor caso
acotado), no un descuido. Pero para tu corrida concreta significa que **hoy terminaría
peor que hace 12 horas**, no mejor.

## Las cinco causas, en orden de impacto

### 1. `max_iterations` es una clave muerta

```bash
grep -rn "max_iterations" --include=*.py .    # → sin resultados
```

Sólo existe en `pragma.yaml:11`. Fue una opción real del scraper viejo, pre-microkernel
(vive en el historial hasta `500f974`), y sobrevivió en el YAML como fósil.

El descarte es silencioso, en `core/config.py:124-127`:

```python
valid = {f.name for f in fields(self)}
for key, val in data.items():
    if key in valid and val is not None:   # las demás se caen sin decir nada
        setattr(self, key, val)
```

**Tu `pragma.yaml` tiene seis claves muertas más**, todas ignoradas igual: `scraper`,
`generator`, `logs_dir`, `progress_logs_dir`, `graph_logs_dir`, `batch_size`. De las
catorce claves top-level del archivo, **la mitad no hace nada**; las que sí son
`agent`, `graph_store`, `out_dir`, `headless`, `wait_seconds`, `agents` y
`graph_stores`.

### 2. Sin `max_pages`, nada acota el crawl

`core/config.py:49` → `max_pages: Optional[int] = None`, y el comentario lo dice:
*"Total pages before stopping; None = unbounded"*.

Es el único freno global que existe. `MechanicalCrawler._worker` lo consulta en
`loop.py:106`; con `None` esa guarda no corre nunca y el crawl termina sólo cuando la
frontera de URLs se vacía sola.

### 3. Regresión del PR #38: tu `pragma.yaml` ya no se lee

Esto es nuevo, lo introdujo `cc8273d`, y es el hallazgo más importante para trabajar de
acá en adelante:

| Archivo | Ruta que usa | Commit |
|---|---|---|
| `core/wizard.py:16` | `PRAGMA_YAML = "pragma.yaml"` (raíz) | sin cambios desde siempre |
| `core/config.py:117` | `Path("config/pragma.yaml")` | **cambiado en `cc8273d`** |

Antes de `cc8273d` ambos decían `pragma.yaml`. El refactor movió el lector y no el
escritor. Resultado hoy, con `python cli.py <url>` sin `-c`:

- busca `config/pragma.yaml`, que **no existe** (en `config/` sólo está
  `pragma.example.yaml`, y `config/pragma.yaml` está en `.gitignore:2`);
- `_apply_yaml` devuelve sin cargar nada y **sin imprimir** `Loaded config from …`;
- corre con puros defaults: `graph_store=memory` (¡no neo4j!), `out_dir=data/output`,
  `wait_seconds=1.0`, `page_concurrency=4`, `max_pages=None`.

O sea: hoy tu configuración entera se ignora. La ausencia de la línea
`Loaded config from …` al arrancar es el síntoma para confirmarlo.

> En la corrida de 12 h (11–12 de agosto, `debug_logs/www.empanad.app__2026081*`) el
> código era **anterior** a `cc8273d`, así que ahí el YAML **sí** se leía. Por eso esa
> corrida usó neo4j y escribió en `docs/`. Pero `max_iterations` ya era clave muerta
> también entonces: el crawl estuvo ilimitado igual, por la causa 1.

### 4. Cada navegación re-encola la página: coste cuadrático

Este es el mecanismo que convierte "sitio grande" en "12 horas".

En `page_visitor/visitor.py:234-240`, cuando un click navega de verdad, el pase de esa
página **se corta** (`break`). `outcomes.py:86` marca `interrupted_by_navigation = True`,
y `loop.py:122-125` re-encola la página:

```python
if result.interrupted_by_navigation:
    self._frontier.requeue(result.resolved_url)
else:
    self.tracker.mark_visited(key)
```

En la rama re-encolada **no se llama `mark_visited`**, y `requeue()` (`frontier.py:67-72`)
puentea a propósito *todas* las guardas — scope, dedup y `max_visits_per_route_shape`.

La consecuencia: **una página con `n` componentes que navegan necesita `n+1` visitas
completas para drenarse**, y cada visita re-hace un `discover_page` entero (settle wait,
extracción de componentes, links, red, metadata). Es O(n²) en páginas con muchos links.

**No existe ningún contador de re-encolados.** El único freno posible es `max_pages`
— que es `None`.

> Hasta el PR #40 había además un techo *dentro* de cada visita
> (`element_budget * max_passes_per_page`, 200 × 10 = 2000 interacciones). No limitaba
> las revisitas — se lo confunde fácil por el nombre — pero sí acotaba cuánto podía
> durar una sola de ellas. Ese techo ya no existe: ver §5.

### 5. (Nuevo en el PR #40) El bucle por página ya no tiene techo

`d59ce99` eliminó `element_budget` y `max_passes_per_page` de todas las capas y dejó el
bucle de `PageVisitor.visit` así (`visitor.py:147`):

```python
# No numeric ceiling - terminates via frontier exhaustion or a break below
while idx < len(frontier):
```

El problema es que **`frontier` es la misma lista que el cuerpo del bucle hace crecer**.
En `outcomes.py:130`, cada interacción que revela componentes nuevos hace:

```python
frontier.append(candidate)
```

O sea: la condición de corte es `idx < len(frontier)`, `idx` sube de a uno por
iteración, y `len(frontier)` puede subir más rápido. Antes el `interactions_done <
max_total_interactions` cortaba eso a las 2000; ahora nada lo hace.

Hay tres guardas que salvan el caso normal — `seen_paths_this_pass`,
`tracker.is_interacted` y la exclusión de widgets que churnean — así que un DOM finito
termina. Pero una página que **acuña paths nuevos** (scroll infinito, chat en vivo, un
widget que se regenera con selectores frescos) no termina nunca, y ya no queda backstop
numérico detrás.

Ezequiel documentó exactamente este tradeoff en el commit y borró a propósito el
fixture `tests/fixtures/mechanical/infinite_reveal.html` y su test, "since no automated
test can terminate against that fixture anymore". La decisión es defendible — prioriza
completitud del grafo — pero es justo el escenario de tu sitio con "demasiadas
pantallas".

### Y por qué encima *parecía* colgado

Al terminar el crawl vienen `F + N + N/5 + 1 + S` llamadas al modelo, todas mudas, con
`agents.local.timeout: 1800`. Es el tema de
[`plan-progreso-en-terminal.md`](plan-progreso-en-terminal.md). No causó las 12 h, pero
hizo imposible saber si seguía viva.

## Qué hacer

### Ahora mismo, sin tocar código

```bash
python cli.py https://tu-sitio --config pragma.yaml --max-pages 40
```

`--max-pages` es lo que creías que hacía `max_iterations`. El `--config` explícito es
lo que sortea la regresión §3. Verificá que aparezca `Loaded config from pragma.yaml`.

Y arreglá el YAML: renombrá `max_iterations: 40` → `max_pages: 40` y borrá las otras
seis claves muertas.

**Ojo con el PR #40**: `--element-budget` y `--max-passes-per-page` ya no existen como
flags. Si los tenías en algún script, ahora es un error de argumento, no un valor
ignorado. Y `--max-pages` pasó de ser *un* freno a ser **el único**.

### Arreglos de código, por orden

1. **Unificar la ruta del config** (§3) — una línea, `core/config.py:111` vuelve a
   `Path("pragma.yaml")`, o el wizard pasa a escribir en `config/`. Hay que elegir una;
   hoy están en desacuerdo. Es un bug de regresión, no un cambio de diseño.
2. **Avisar de claves desconocidas** (§1) — que `_apply_yaml` imprima
   `Ignorando clave desconocida 'max_iterations'` en vez de callarse. Diez líneas, y
   convierte esta clase entera de bug en un mensaje al arrancar.
3. **A′ de `plan-progreso-en-terminal.md`** — la línea por visita que distingue únicas
   de revisitas. Subió de prioridad: con §5 encima, hace falta poder ver si el crawl
   está atascado en *una* página antes de decidir qué backstop reponer.
4. **Decidir qué backstop reponer** (§4 + §5) — acá hay una conversación con Ezequiel,
   no un fix obvio. Él sacó el techo por página a propósito, para no perder cobertura
   del grafo. Las dos cosas se pueden tener, pero hay que elegir la forma:
   - un tope de **tiempo** por visita en vez de un tope de interacciones (no sesga qué
     componentes se exploran, sólo cuánto se insiste);
   - un tope de re-encolados por `route_shape` (§4), que es un eje distinto del que él
     sacó y no reintroduce el problema que le molestaba;
   - `max_pages` con un default no-`None`, que es el freno global que hoy nadie pone.

   Los tres son compatibles con su objetivo. Lo que no conviene es dejar las cinco sin
   ninguna.

## Lo que este diagnóstico **no** afirma

No reproduje la corrida de 12 h: no hay Docker/neo4j levantado acá, y los
`debug_logs/` de esas corridas están vacíos de artefactos por página.

Las causas 1, 2, 3 y 5 están verificadas leyendo el código y el historial de git, y son
deterministas — §5 además está admitida explícitamente en el mensaje de `d59ce99`.

La causa 4 es una lectura del flujo de control: sólida, pero **no medida**. El punto 3
de arriba existe justamente para medirla antes de arreglarla.
