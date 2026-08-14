# Plan: decir en la terminal qué está haciendo el sistema

> Escrito originalmente en `progress-output`, sacada de `main` en `c8e86d3`.
> **Revisado el 2026-08-14** contra `main` post-refactor (`ec03ea8`), después del merge
> del PR #38 de Ezequiel.

## Estado tras el refactor: sigue vigente

El refactor movió archivos, no cambió el problema. Concretamente:

- `cc8273d` aplanó `src/` a paquetes top-level, así que **todo `src/core/…` del plan
  original es hoy `core/…`**. Los generadores nunca se movieron.
- `f6b1196` + `8f7d4e2` partieron `spiders/` en `browser/`, `content/` y
  `orchestration/`. Nada de eso toca el bloque post-crawl.
- El conteo que motivó el plan **no cambió**: en todo el camino post-crawl hay cuatro
  `print`, y tres son de error (`engine.py:221`, `engine.py:229`, `pipeline.py:92`;
  el único informativo es `engine.py:325`, el pase de medición).

Los niveles A, B, C y D se mantienen tal cual. Lo único que cambia son los anclajes de
línea, actualizados abajo, y **una recomendación que hay que dar vuelta** (ver
"Corrección al plan original").

## El problema, medido

Cuando termina el crawl, crawl4ai deja de imprimir sus líneas `FETCH` / `SCRAPE` /
`COMPLETE` y la terminal queda muda. Parece colgado. No lo está: quedan varias fases
secuenciales, y las más lentas son llamadas al modelo.

| Fase | Dónde (post-refactor) | Llamadas al modelo |
|---|---|---|
| Familias de componentes | `core/engine.py:317` → `generators/component_family_narrator.py:72` | **una por familia** |
| Grafo de requests | `core/engine.py:318` | ninguna, es rápido |
| Pase de medición (si está activo) | `core/engine.py:324` | ninguna, pero navega **cada página**; imprime sólo al terminar (`core/engine.py:325`) |
| PRD: catálogo por página | `generators/graph_prd_synthesizer.py:160` | **una por página** |
| PRD: resumen por lote | `generators/graph_prd_synthesizer.py:192` | una cada `prd_synth_batch_size` páginas |
| PRD: reducción final | `generators/graph_prd_synthesizer.py:215` | una |
| Gherkin: títulos | `generators/gherkin.py:151` | **una por escenario** |
| Resto de documentos | `generators/pipeline.py` | ninguna, son deterministas |
| Manifiesto e índice | `core/engine.py:341`, `core/engine.py:361` | ninguna |

Con `N` páginas, `F` familias y `S` escenarios son `F + N + N/5 + 1 + S` llamadas al
modelo, todas mudas. Con un modelo local remoto (`agents.local.timeout: 1800` en la
config real de este proyecto) eso puede ser muchos minutos sin una sola línea.

## Cómo ver el avance hoy, sin tocar nada

Sirve mientras el plan no esté implementado, y sigue sirviendo después.

Los documentos se escriben de a uno, en orden:

```bash
ls -lt docs/ | head
```

El `_master_` siempre es el último. Y el grafo se puebla en vivo:

```cypher
MATCH (f:ComponentFamily {site: 'www.empanad.app'}) RETURN count(f)
```

Si ese número sube, está narrando familias y no está trabado.

---

## Corrección al plan original: el crawl también necesita una línea

El plan original decía, en "Lo que no hay que hacer":

> **No meter progreso en el bucle del crawl.** Crawl4ai ya imprime por página […] El
> problema es el post-crawl, que es secuencial.

**Eso era incorrecto, y la corrida de 12 horas lo demuestra.** El razonamiento suponía
que si crawl4ai imprime una línea por página, entonces ver líneas equivale a ver
avance. No equivale: el crawl **revisita la misma página muchas veces** por diseño
(cada navegación física corta el pase y re-encola la página — ver
`spiders/orchestration/mechanical_loop/loop.py:122-125`), y una revisita imprime
exactamente igual que una página nueva. Una corrida atascada y una corrida sana se ven
idénticas en la terminal.

Lo que falta no es una línea por página — esa ya está — sino **el denominador**:

```
página 37 (12 únicas, 25 revisitas) — frontera: 240 pendientes
```

Con eso, las 12 horas se habrían diagnosticado en dos minutos: el contador de únicas
casi quieto y el de revisitas subiendo es la firma exacta del problema.

**Dónde**: `MechanicalCrawler._worker`, `loop.py:120-128`. Ya existen ahí
`self._pages_visited` y el `if result.interrupted_by_navigation` que distingue los dos
casos; no hay que calcular nada nuevo.

**La objeción original sigue siendo válida a medias**: con `page_concurrency: 4` la
salida se entrelaza. La respuesta no es callarse, es que **cada línea diga qué worker
la emitió** y que sea una sola línea por visita, no un bloque.

Esto es un **Nivel A′**, del mismo tamaño y riesgo que el A, y con más valor
diagnóstico que todo el resto del plan junto.

---

## Nivel A — Una línea por fase

**Qué**: un `print` al empezar cada fase del bloque post-crawl, con el trabajo que
viene por delante cuando se conoce.

```
Agrupando componentes en familias...
Narrando 12 familias (12 llamadas al modelo)...
Infiriendo endpoints...
Generando 11 documentos...
```

**Dónde**: `Engine._run_async`, entre `core/engine.py:317` y `core/engine.py:361`.
Nada más.

**Por qué primero**: contesta *"¿terminó el crawl o se colgó?"*, que es la pregunta
inmediata, y no toca ninguna firma ni ninguna decisión de arquitectura.

**Criterio de terminado**: una corrida completa del CLI no tiene ningún tramo de más
de una fase sin salida.

**Coste**: diez `print`. Sin dependencias nuevas.

---

## Nivel B — Contador dentro de los dos bucles de modelo

**Qué**: progreso por ítem donde el tiempo se va de verdad.

```
  familia 3/12: "confirma o envía una acción"
  página 7/40: shop.example/cart
```

**Dónde**, exactamente dos lugares:

- `narrate_family_purposes` — el `for family in families` de
  `generators/component_family_narrator.py:72`.
- `GraphPRDSynthesizer._narrate_page_catalog` — el `for page_url in sorted(...)` de
  `generators/graph_prd_synthesizer.py:160`.

Opcionalmente un tercero, `gherkin.narrate_titles`
(`generators/gherkin.py:151`), que sólo pesa si el sitio produjo muchos escenarios.

**Los totales ya se conocen** antes de entrar al bucle (`len(families)`,
`len(ledger)`), así que no hay que calcular nada nuevo ni recorrer dos veces.

**Por qué es lo que de verdad importa**: distingue *"está pensando"* de *"está
trabado"*. Una línea por fase te dice que arrancó; un contador que avanza te dice que
sigue vivo. Si el contador se queda en `3/12` diez minutos, el problema es el modelo,
y eso es información accionable.

**Criterio de terminado**: con `--agent mock` (respuestas instantáneas) el contador
llega al total en las dos fases. Con un agente lento se ve avanzar.

**Coste**: dos `print` dentro de bucles que ya existen.

### Detalle a decidir al implementar

Estos módulos son puros hoy salvo por el `agent` que reciben. Meter `print` los ata a
stdout. Dos salidas:

- **Aceptarlo**: son código de aplicación, no librería, y el resto del proyecto ya
  imprime (`generators/pipeline.py:92`, `core/engine.py:325`). Es lo más simple y
  probablemente lo correcto para A y B.
- **Anticipar el Nivel C**: pasar un callable opcional `on_progress` con default
  `None`. Más ceremonia ahora, menos retrabajo si C llega.

Recomendación: aceptar el `print` en A y B. Si C llega, ahí se refactoriza con el
Nivel C completo delante, no adivinando.

---

## Nivel C — Un reporter de progreso como abstracción

**Qué**: un protocolo chico (`ProgressReporter`, con algo como `phase(name)` y
`step(done, total, label)`), pasado por `DocumentRequest` y por los dos narradores.
El CLI provee la implementación que imprime; los tests, una que registra llamadas.

**Cuándo hacerlo**: cuando aparezca un **segundo consumidor** del progreso. Hoy hay
uno solo (la terminal), y una abstracción con un solo implementador es ceremonia.
Los candidatos reales que lo justificarían:

- el menú interactivo (`core/app.py`), que hoy lanza el CLI como subproceso y
  sólo ve su stdout;
- una UI (Nivel D);
- tests que quieran afirmar sobre las fases sin capturar stdout.

**Qué habilita que A y B no**: que el progreso sea *dato* y no *texto*. Un `print` no
se puede testear sin `capsys` ni renderizar de otra forma.

**Criterio de terminado**: un test afirma la secuencia de fases sin capturar stdout, y
el CLI sigue mostrando exactamente lo mismo que antes.

**Coste**: un protocolo nuevo en `core/`, un campo más en `DocumentRequest`, un
parámetro opcional en dos narradores, y una implementación en el CLI. Nada difícil,
pero toca varias firmas.

---

## Nivel D — Barras de progreso / UI

> **No hacer hasta que Julieta lo pida explícitamente.** Queda escrito para que la
> decisión esté tomada de antemano, no para ejecutarlo con el resto.

**Qué**: `rich` o `tqdm` para barras, spinners y salida en vivo que se sobrescribe.

**Por qué queda último**:

- Es una **dependencia nueva de runtime**. Hoy el proyecto tiene `questionary` para
  prompts, pero nada para renderizar progreso, y las dependencias de runtime se pagan
  para siempre.
- A + B ya contestan la pregunta que motivó todo esto. D es comodidad, no información.
- Una barra que se sobrescribe **pelea con el resto de la salida**: crawl4ai imprime
  sus propias líneas, y el pase de medición y los errores de generador también. Sale
  bien sólo si algo coordina toda la salida del proceso, que es justamente el
  Nivel C.

**Prerrequisito real**: el Nivel C. Sin un reporter, una barra queda cableada dentro
de los generadores y no se puede apagar ni redirigir.

**Si se hace**: `rich` por sobre `tqdm` — ya resuelve la convivencia entre logging y
barras, que es el problema difícil acá.

---

## Orden y estado

| Nivel | Estado | Depende de |
|---|---|---|
| **A′ — línea por visita del crawl, con únicas vs. revisitas** | **pendiente, prioridad 1** | nada |
| A — línea por fase | **hecho (2026-08-14)** | nada |
| B — contador por ítem | **hecho (2026-08-14)** | nada |
| C — reporter | pendiente, sólo con un segundo consumidor | A y B hechos |
| D — UI | **congelado hasta que Julieta lo pida** | C |

A′ quedó pendiente a pedido de Julieta, que pidió A y B solos. Sigue siendo el único
que ataca la falla que costó 12 horas.

### Qué quedó implementado en A y B

Los mensajes se escribieron **en inglés**, no en español como los ejemplos de este
plan. Los ejemplos eran ilustrativos; los cuatro `print` que ya existían en el
proyecto (`core/engine.py:221`, `:229`, `generators/pipeline.py:92`) son todos en
inglés, y mezclar los dos idiomas en la misma salida es peor que cualquiera de los
dos. Cambiarlo es reemplazar literales, si preferís español.

| Dónde | Qué imprime |
|---|---|
| `core/engine.py` | `Crawl finished. Grouping components into families...`, `Inferring API endpoints...`, `Measurement pass: ...`, `Writing run manifest and index...` |
| `core/engine.py:_apply_component_families` | `Grouped N components into M families.` |
| `generators/component_family_narrator.py` | encabezado + `  family i/n: tag (type)` |
| `generators/graph_prd_synthesizer.py` | encabezado + `  page i/n: url`; `  section i/n`; la línea de reducción final |
| `generators/gherkin.py` | encabezado + `  scenario i/n: origen -> destino` |
| `generators/pipeline.py` | `Generating N documents...` + `[i/n] nombre` por documento |

Dos decisiones que vale la pena registrar:

- **El denominador cuenta llamadas al modelo, no ítems.** Familias sin texto y páginas
  sin hechos se saltean sin gastar una llamada; si el total contara ítems, el contador
  terminaría en `10/12` y parecería colgado justo al final. Verificado: 3 familias, 1
  sin texto, el contador llega a `2/2`.
- **La línea se imprime antes de la llamada, no después.** El objetivo es mostrar en
  qué ítem está bloqueado ahora, no cuál terminó recién.

`pipeline.py` imprime por documento y no sólo el total, porque el costo entre
generadores es muy desparejo: casi todos son deterministas e instantáneos, pero `prd`
y `gherkin` hacen una llamada por página y por escenario. Un solo
`Generating 11 documents...` escondería una hora adentro de uno de los once.

## Lo que no hay que hacer

- **No agregar `rich`/`tqdm` para A′, A ni B.** No hacen falta y son dependencia
  permanente.
- ~~No meter progreso en el bucle del crawl.~~ **Revocado** — ver "Corrección al plan
  original". Sí va, con la forma que se describe ahí: una línea por visita, con worker
  id y con el desglose únicas/revisitas.
- **No convertir esto en logging estructurado.** Ya existe `CrawlDebugLog` para el
  registro forense por corrida; esto es otra cosa: decirle a una persona que mira la
  terminal que el proceso sigue vivo. Mezclarlos haría los dos peor.

## Relación con el bug de la corrida de 12 horas

El progreso en terminal **no arregla** ese bug, lo hace visible. Las causas están
documentadas aparte, en `research/diagnostico-corrida-sin-fin.md`. El orden sano es:
A′ primero (para poder ver qué pasa), después los arreglos de ese diagnóstico.

**Actualización tras el PR #40 (`d59ce99`, 2026-08-14)**: Ezequiel eliminó el techo de
interacciones por página, que era el último backstop numérico del crawl. Eso vuelve a
A′ más necesario, no menos, y además le cambia la forma.

Con el techo puesto, una página atascada terminaba igual (a las 2000 interacciones) y
el crawl seguía; alcanzaba con contar visitas únicas vs. revisitas. Sin techo, el crawl
puede quedarse **para siempre dentro de una sola visita**, sin emitir ni una línea:
`while idx < len(frontier)` sobre una lista que el propio cuerpo del bucle hace crecer
(`outcomes.py:130`).

Así que A′ necesita una línea más de las que decía arriba — **progreso dentro de la
visita**, no sólo por visita:

```
worker 2 | página 37 (12 únicas, 25 revisitas) | frontera: 240 pendientes
  ↳ interacción 118, frontera de la página: 213 y subiendo
```

Ese "y subiendo" es la firma exacta del §5 del diagnóstico, y hoy es invisible.

## Pipeline de calidad

Aplica `CLAUDE.md`: `python-clean-code` mientras se escribe, `clean-code-principles`
antes de mostrar el diff (sobre todo para el Nivel C, que es el único con decisiones
de diseño), y `anti-slop` sobre el texto de los mensajes — que son prosa que ve un
usuario y merecen ser específicos: `"Narrando 12 familias"` y no
`"Procesando datos..."`.
