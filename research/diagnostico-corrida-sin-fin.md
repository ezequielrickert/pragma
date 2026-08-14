# Diagnóstico: la corrida de 12 horas que nunca terminó

> Escrito el 2026-08-14 contra `main` en `ec03ea8` (post-merge del PR #38).
> Pregunta que lo motiva: *"corrí una URL con demasiadas pantallas, estuvo 12 h y nunca
> terminó; algo hace que se pase de las 40 iteraciones del yaml"*.

## Respuesta corta

**Las 40 iteraciones nunca existieron.** `max_iterations` no es una opción de este
programa: no aparece en ningún `.py` del repo, sólo en tu `pragma.yaml`. El cargador de
config descarta en silencio toda clave que no sea un campo del dataclass, así que esa
línea nunca hizo nada.

El límite real se llama `max_pages`, y su default es `None` — **crawl ilimitado**.

Y el refactor de Ezequiel **no lo arregla; agrega un problema nuevo** (§3).

## Las cuatro causas, en orden de impacto

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

### 3. Regresión del refactor: tu `pragma.yaml` ya no se lee

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

Cuidado con el nombre: `max_passes_per_page` **no** limita esas revisitas. Se usa en un
solo lugar, `visitor.py:142`, como techo *dentro de una visita*:

```python
max_total_interactions = self.element_budget * self.max_passes_per_page   # 200 * 10 = 2000
```

**No existe hoy ningún contador de re-encolados.** El único freno posible es
`max_pages` — que es `None`.

### Y por qué encima *parecía* colgado

Al terminar el crawl vienen `F + N + N/5 + 1 + S` llamadas al modelo, todas mudas, con
`agents.local.timeout: 1800`. Es el tema de
[`plan-progreso-en-terminal.md`](plan-progreso-en-terminal.md). No causó las 12 h, pero
hizo imposible saber si seguía viva.

## Qué hacer

### Ahora mismo, sin tocar código

```bash
python cli.py https://tu-sitio --config pragma.yaml --max-pages 40 --page-concurrency 4
```

`--max-pages` es lo que creías que hacía `max_iterations`. El `--config` explícito es
lo que sortea la regresión §3. Verificá que aparezca `Loaded config from pragma.yaml`.

Y arreglá el YAML: renombrá `max_iterations: 40` → `max_pages: 40` y borrá las otras
seis claves muertas.

### Arreglos de código, por orden

1. **Unificar la ruta del config** (§3) — una línea, `core/config.py:117` vuelve a
   `Path("pragma.yaml")`, o el wizard pasa a escribir en `config/`. Hay que elegir una;
   hoy están en desacuerdo. Es un bug de regresión, no un cambio de diseño.
2. **Avisar de claves desconocidas** (§1) — que `_apply_yaml` imprima
   `Ignorando clave desconocida 'max_iterations'` en vez de callarse. Diez líneas, y
   convierte esta clase entera de bug en un mensaje al arrancar.
3. **Acotar los re-encolados** (§4) — un contador por `route_shape` en el camino de
   `requeue`, con tope. Es el arreglo real del coste cuadrático y el único con decisión
   de diseño de por medio: hay que elegir el tope sin romper el drenado legítimo de
   páginas con muchos links.
4. **A′ de `plan-progreso-en-terminal.md`** — la línea por visita que distingue únicas
   de revisitas. Idealmente antes que el punto 3, para poder medir si funcionó.

## Lo que este diagnóstico **no** afirma

No reproduje la corrida de 12 h: no hay Docker/neo4j levantado acá, y los
`debug_logs/` de esas corridas están vacíos de artefactos por página. Las causas 1, 2 y
3 están verificadas leyendo código y el historial de git, y son deterministas. La
causa 4 es una lectura del flujo de control, sólida pero **no medida** — el punto 4 de
arriba existe justamente para medirla antes de arreglarla.
