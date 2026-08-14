# Plan: corridas cortas reanudables, o una larga, a elección

> Escrito el 2026-08-14 contra `main` en `2c4e2f3` (post PR #40).
> Nace de `research/diagnostico-corrida-sin-fin.md`: una corrida de 12 h que nunca
> terminó y hubo que cortar a mano.

## El problema en una línea

Hoy el crawl sólo tiene un final: agotar la frontera de URLs. Si el sitio es grande —o
si una sola página no termina nunca, que es el §5 del diagnóstico— no hay corte, no hay
documentos, y lo único que queda al matarlo es un grafo a medias sin nada que lo lea.

## Lo que ya existe y no hay que construir

Esto es lo más importante del plan: **la mitad está hecha y sin cablear.**

| Pieza | Dónde | Estado |
|---|---|---|
| Estado `Pending`/`Finished` por página | `_neo4j_cypher_helpers.py:29` | funciona |
| Nodo `Page` para todo URL descubierto | `record_links`, `record_edge` | funciona |
| Lector de la to-do list | `GraphStore.get_pending(site, limit)` | **implementado en los dos stores, no lo llama nadie** |
| No re-encolar lo ya visitado | `mechanical_loop/frontier.py:38` | funciona |
| `is_visited` leyendo del grafo | `graph_sink/tracker.py:37` | funciona |
| Saltar lo ya interactuado | `tracker.is_interacted`, persistido | funciona |
| No purgar el grafo al arrancar | `--no-fresh` | funciona, y está documentado como "resume a previous run's progress" |
| Degradar documento por documento | `generators/pipeline.py:92` | funciona |
| Cobertura terminadas/totales | `graph_store.count_visited` | funciona |

`get_pending()` es literalmente la to-do list persistida, con lector, sin usar. Todo URL
que se descubrió pero no se visitó ya está en el grafo como `Page {status: 'Pending'}`,
porque tanto los targets de links como los de navegación pasan por
`_page_ensure_clause`, que crea el nodo con ese default.

**Lo único que falta para reanudar** es que `MechanicalCrawler.crawl_site` siembre la
frontera con `get_pending(site)` además de con `start_url`.

## Las dos preguntas que dispararon este plan

### 1. ¿Se puede elegir entre varias corridas cortas y una sola larga?

Sí — y la mejor forma no es tener dos modos, sino **que no haya modos**.

#### La versión mala (la que había escrito primero)

Un `crawl_mode: one_shot | incremental` con dos caminos de código. El problema es
evidente en cuanto se escribe: son dos caminos que hay que mantener de acuerdo, y todo
lo que se agregue después hay que agregarlo dos veces o se desincronizan. La pregunta
"¿da lo mismo una larga que varias cortas?" no debería depender de que alguien se
acuerde de mantener la paridad.

#### La versión buena: un solo camino, el presupuesto es un número

El crawl es **siempre** reanudable y **siempre** acotado. "Una larga" es simplemente el
presupuesto en infinito:

```yaml
crawl_budget:
  pages: null      # null = sin límite
  nodes: null
  minutes: null
```

Sin configurar nada, los tres son `null`, el bucle corre una sola vez hasta agotar la
frontera, y el comportamiento es exactamente el de hoy. Con cualquiera puesto, corta y
deja el resto `Pending`. **No hay dos modos que puedan divergir, porque hay un solo
camino de código.**

La estructura queda:

```
sembrar frontera desde start_url + get_pending(site)
while frontier no vacía and presupuesto no agotado:
    visitar página
post-procesar (familias, endpoints, documentos)
```

Con presupuesto infinito ese `while` se agota solo una vez y post-procesa una vez. Con
presupuesto finito corta antes, post-procesa igual, y la corrida siguiente entra por el
mismo `while` con la frontera sembrada desde `get_pending()`.

#### La superficie concreta: `pages`, y un flag para apagarlo

Decisión tomada (Julieta, 2026-08-14): **cortar por páginas.** El caso de uso es
"20 páginas, miro los datos, sigo con otras 20", y `pages` es la unidad que se
corresponde con eso. `nodes` y `minutes` quedan como opcionales, no como el default.

```yaml
crawl_budget:
  pages: 20        # el corte normal
  nodes: null      # opcional
  minutes: null    # opcional, red de seguridad
```

Y para la corrida larga —dejarlo toda la noche— un flag que apaga el presupuesto sin
tener que editar el YAML:

```bash
python cli.py https://sitio --full            # ignora crawl_budget, corre hasta agotar
python cli.py https://sitio --max-pages-per-run 50   # override puntual
```

`--full` no es un segundo modo: pone los tres presupuestos en `null` y entra por el
mismo `while`. Un solo camino de código, dos ergonomías.

**El riesgo de cortar sólo por páginas, dicho una vez**: si una página cae en el §5 del
diagnóstico (bucle de revelado sin techo desde el PR #40), nunca termina, el contador de
páginas nunca avanza, y el corte por `pages` no llega nunca. Volvés a la corrida de 12 h.
Por eso `minutes` conviene igual, seteado alto —digamos 90— como red que normalmente no
se toca. No cambia el comportamiento normal y te devuelve la terminal en el caso malo.

**Y `fresh` deja de ser un flag que hay que acordarse.** Con un solo camino, purgar es
una acción explícita y aparte (`--purge`, o `fresh: true` pedido a mano), no el default
que silenciosamente borra la to-do list que venías a continuar.

### 1b. ¿Qué falta para que de verdad den lo mismo?

Tres condiciones. Una ya se cumple, dos no.

**(a) El post-proceso tiene que ser función pura e idempotente del grafo. ✅ Ya lo es.**

`record_component_families` y `record_inferred_requests` son **rebuild completo**: borran
todo lo del sitio y lo recrean desde el ledger acumulado. Correr el post-proceso cinco
veces converge al mismo estado que correrlo una vez al final. Esto es la base de todo y
sale gratis.

**(b) Todo contador que decida algo tiene que vivir en el grafo, no en memoria. ❌ Falta uno.**

`UrlFrontier._route_shape_visits` (`frontier.py:33`) es un `Dict` en memoria, y
`grep route_shape` sobre `database/` no devuelve nada: **no se persiste**.

Consecuencia concreta, y es la respuesta directa a tu pregunta: con
`max_visits_per_route_shape: 1`, una corrida larga muestrea **una** URL por forma de
ruta. Cinco corridas cortas resetean el contador cinco veces y muestrean **hasta cinco**.
Hoy varias cortas crawlean *más* que una larga, y el grafo sale distinto.

Arreglo: guardar `route_shape` como propiedad del nodo `Page` al crearlo, y derivar el
contador con una query en vez de mantenerlo en memoria. No hace falta estado nuevo, sólo
dejar de tenerlo dónde se pierde.

**(c) El orden de visita tiene que ser el mismo. ❌ Hoy no lo es.**

Una corrida larga visita en el orden de la cola viva (BFS desde la semilla). Una
reanudada siembra desde `get_pending()`, que ordena `ORDER BY p.url` — alfabético.

Con el cap de (b) puesto, el orden **decide qué URL de cada forma de ruta se queda**, así
que dos órdenes distintos dan dos grafos distintos.

Arreglo: número de secuencia de descubrimiento como propiedad de `Page`, y `get_pending`
ordenando por él. Así la reanudación reproduce el orden que la corrida larga habría
seguido.

### 1c. Lo que **no** se puede igualar, y hay que aceptar

- **La narración del modelo.** Dos llamadas con el mismo prompt no dan el mismo texto.
  El grafo puede ser idéntico; los documentos van a diferir en redacción siempre. Con el
  caché de catálogos por página esto se reduce, no se elimina.
- **Un sitio que cambia entre corridas.** Inherente a reanudar. Una larga ve el sitio en
  un instante; cinco cortas lo ven en cinco. No hay arreglo, sólo conciencia.
- **El presupuesto por `minutes` es irreproducible por definición.** Corta en un punto
  que depende de la velocidad de la máquina y de la red. Es el único que garantiza
  terminar (§1) y el único que rompe la reproducibilidad — tensión real, sin salida
  elegante. Si querés corridas comparables entre sí, cortá por `pages` o `nodes`; usá
  `minutes` como red de seguridad, con un valor alto que normalmente no se alcance.

### 2. ¿Las familias se rehacen o se van apendeando?

**Se rehacen enteras, siempre. Tu preocupación no ocurre.**

`neo4j_component_family_store.py:99` arranca con:

```cypher
MATCH (f:ComponentFamily {site: $site}) DETACH DELETE f
```

y después recrea todo desde cero. Y el insumo es
`build_component_families(flat_component_ledger(graph_store, site))`, que lee **todos**
los componentes del sitio en el grafo — los de esta corrida y los de todas las
anteriores.

O sea, concretamente sobre tu ejemplo: un componente descubierto en la página 1 durante
la corrida 1 **sí** se re-clusteriza en la corrida 5 con la evidencia de la página 20. No
queda pegado a una familia peor por no haberse revisitado. La doc de la interfaz lo dice
explícito: *"cluster membership isn't kept stable across runs"*, y es a propósito.

#### Pero esto rompe algo que te dije antes

En la conversación te propuse "cachear la narración: narrar sólo lo que tenga `purpose`
vacío" como mitigación del costo de modelo. **Para familias eso está mal**, y tu
pregunta es justamente lo que lo expone.

Si las familias se re-derivan en cada corrida, la familia de la corrida 1 no es la misma
entidad que la de la corrida 5: cambió de miembros, y puede haberse partido o fusionado.
No hay una clave estable contra la cual cachear, y peor: si el propósito viejo
sobrevive a un re-clustering, queda describiendo un grupo que ya no es ese.

Además el `DETACH DELETE` borra los `purpose` anteriores, así que hoy no hay ni siquiera
de dónde leerlos.

Para **catálogos de página** el caché sí es correcto y seguro: la clave es `page_url`,
que es estable entre corridas, y una página terminada no cambia. Y ahí está el volumen
real — una llamada por página contra una por familia, y las páginas son muchas más.

#### ¿Y no conviene apendear familias en vez de borrar y rehacer?

Pregunta de Julieta: *"en vez de delete y hacerlos de cero, ver los nodos y si alguno
concuerda mejor con otra familia apendearlo sin borrar todo"*.

El instinto —no rehacer trabajo— es correcto, pero **el clustering es la parte que no
cuesta nada**. `generators/component_family.py` lo dice en su primera línea: *"Pure,
deterministic inference […] no I/O, no LLM"*. Es CPU: bucketear por
`(tag, component_type)` y Jaccard sobre `css_class` dentro de cada bucket. Rehacerlo
entero es gratis.

Lo que cuesta es `narrate_family_purposes`: una llamada al modelo por familia.

Y apendear tendría dos costos reales:

1. **Rompe la equivalencia** que pedimos en §1b. Un clustering incremental depende de
   qué corrida vio qué primero: la familia resultante deja de ser función del ledger y
   pasa a ser función del *historial de corridas*. Varias cortas y una larga dejarían de
   dar lo mismo, que es justo lo que queremos evitar.
2. **"Si concuerda mejor con otra familia" es el rebuild.** Para saber si un componente
   encaja mejor en otro lado hay que compararlo contra todas las familias existentes —
   que es exactamente lo que hace el clustering completo, sólo que con más estado y más
   formas de equivocarse.

**La salida que sí sirve**: seguir rehaciendo el clustering (gratis, correcto), y cachear
la **narración** con una clave que sobreviva al re-clustering — la firma estructural de
la familia:

```
(tag, component_type, common_classes, member_paths ordenados)
```

Si una familia vuelve con firma idéntica, es la misma familia: se reusa su `purpose`. Si
cambió de miembros, se re-narra, que es lo correcto porque el grupo cambió.

En la práctica la mayoría de las familias se estabilizan temprano, así que a partir de
la tercera o cuarta pasada casi todas las llamadas se ahorran — sin perder ni la
corrección del clustering ni la equivalencia.

Esto **corrige lo que dice arriba** ("no cachear familias"): no se puede cachear por
identidad de familia, pero sí por firma. Requiere guardar la firma junto al `purpose`,
que hoy no se hace porque el `DETACH DELETE` borra todo.

**Recomendación**: cachear catálogos de página por `page_url`, cachear propósitos de
familia por firma estructural, y seguir rehaciendo el clustering entero siempre.

## Hallazgo que cambia el plan: `Pending` miente

> Reportado por Julieta el 2026-08-14: corrió `empanad.app` con el `main` actual y
> *"solo recorrió completa una sola página, y dejó 2 sin visitar"*.

Investigado. **`is_in_scope` se usa en exactamente un lugar de todo el crawl**:

```
spiders/orchestration/mechanical_loop/frontier.py:42
```

Es decir, sólo la **frontera** filtra por dominio. El **sink que crea los nodos, no**.
`GraphStoreSink.record_inventory` (`sink.py:139-149`) arma su `link_batch` filtrando
únicamente por esquema (`http`/`https`) y href no vacío, y se lo pasa a `record_links`,
que hace `MERGE` de un `Page` con `status: 'Pending'` para cada destino.

Consecuencia: **cada link externo —Instagram, Facebook, WhatsApp, Google Maps— queda como
una `Page` en estado `Pending` que nunca, jamás, se va a visitar**, porque la frontera la
rechaza por scope.

Eso explica el síntoma sin necesidad de que haya un bug en el recorrido: las "2 sin
visitar" son con toda probabilidad links externos. El crawl hizo lo correcto; lo que está
mal es **el reporte**.

Y tiene tres consecuencias que este plan tiene que absorber:

1. **`count_visited` es engañoso para siempre.** Cuenta todo nodo `Page` en el total
   (`neo4j_graph_store.py:405`), así que la cobertura nunca puede llegar a 100% en un
   sitio que enlace hacia afuera. El documento de cobertura hereda el error.
2. **El sembrado desde `get_pending()` que propone este plan no funciona como está
   escrito.** Devolvería URLs externas. La frontera las filtraría por scope, así que no
   habría crawl infinito — pero el contador de pendientes nunca bajaría a cero, y no
   habría forma de saber cuándo se terminó. Que es justamente lo que necesitamos para
   "reanudá hasta terminar".
3. **Es prerrequisito, no mejora.** Sin esto, el corte y la reanudación se construyen
   sobre una to-do list que contiene tareas imposibles.

**Arreglo**: que el sink aplique el mismo criterio de scope que la frontera antes de
crear el nodo. Un link fuera de dominio sigue siendo un dato interesante (a dónde manda
el sitio), así que no se descarta: se registra distinto —`status: 'External'`— de modo
que `get_pending` y `count_visited` sólo cuenten lo que de verdad es alcanzable.

**Lo que este hallazgo no descarta**: que además haya páginas *internas* sin visitar. No
lo puedo verificar sin Neo4j y browser levantados. El paso 1 del orden de trabajo (A′,
progreso del crawl) existe justamente para que la próxima corrida lo diga sola — si una
página interna se saltea por el cap de forma de ruta, hoy eso se imprime pero se pierde
entre el ruido de crawl4ai.

## Diseño

### Dónde se corta

En `MechanicalCrawler._worker`, en el mismo lugar donde ya se consulta `max_pages`
(`loop.py:106`):

```python
if self.max_pages is not None and self._pages_visited >= self.max_pages:
    continue  # cap reached - drain without visiting
```

Ese `continue` en vez de un `break` es deliberado y hay que imitarlo: los workers tienen
que **seguir drenando la cola sin visitar**, porque `crawl_site` espera en
`self._frontier.join()` y si los workers dejan de llamar `task_done()` ese join no
vuelve nunca. El presupuesto se engancha exactamente ahí, con la misma forma.

Cortar en borde de página (antes de tomar una URL nueva) y no a mitad de visita:
una visita cortada al medio deja la página `Pending`, que es consistente, pero deja el
grafo más sucio de lo necesario. Vos ya lo habías intuido.

### Cómo se reanuda

En `crawl_site`, antes de arrancar los workers:

```python
self._frontier.enqueue(start_url)
for url in self.tracker.pending_urls():   # -> graph_store.get_pending(site)
    self._frontier.enqueue(url)
```

`enqueue` ya filtra por `is_visited` y por scope, así que sembrar de más es inofensivo.

Un detalle que hay que decidir: **el orden**. `get_pending` devuelve `ORDER BY p.url`,
que es alfabético y arbitrario. Para "varias pasadas controlables" probablemente
convenga priorizar por profundidad o por grado de entrada, pero eso es una mejora
posterior, no un bloqueante.

### Los documentos no se apendean: se re-proyectan (y eso es lo que querías)

Pregunta de Julieta: *"en vez de hacer los doc de 0, que apendee o junte la nueva data
con la data que ya había en esos docs"*.

**Eso ya pasa, por construcción.** La distinción que importa:

- **El grafo acumula.** Con `fresh: false`, la corrida 2 escribe encima del grafo de la
  corrida 1. Al terminar, el grafo tiene las 40 páginas.
- **El documento es una vista del grafo, no un acumulador.** Se genera leyendo el grafo
  entero (`get_progress_table_rows`, `get_component_ledger`, `get_edges`).

Entonces "hacerlo de 0" en la corrida 2 **no** produce el documento de las 20 páginas
nuevas: produce el documento de las 40. Regenerar *es* el merge. No se pierde nada de la
corrida 1.

Además cada corrida escribe archivos nuevos con su propio timestamp
(`DocumentNaming(out_dir, slug, timestamp=run_timestamp)`), así que quedan las dos
versiones y se pueden diffear — que es justo el control que buscabas.

**Y apendear texto sería peor, no mejor.** Un documento apendeado no puede corregir lo
que la corrida anterior escribió y ahora es falso: la cobertura ("20 páginas"), el
resumen del sitio, el grafo de navegación. Quedarían dos secciones contradiciéndose y
ninguna forma de saber cuál vale. La proyección no tiene ese problema porque no hay
estado viejo que sobreviva.

**Lo que sí conviene no rehacer son las llamadas al modelo**, que es probablemente lo que
te hacía ruido. Eso es el caché de narración (paso 7), y ahí sí hay trabajo real que
ahorrar. Rehacer el *documento* es barato; rehacer la *narración* no.

### Documentos parciales

Cuando el corte deja páginas `Pending`, los documentos tienen que decirlo **en el cuerpo
del documento**, no sólo en el manifiesto. Un PRD hecho con el 20% del sitio se lee
igual que uno completo.

Concretamente: un campo en `DocumentRequest.settings` con la cobertura, y un bloque al
principio del master y del PRD del estilo
`Corrida parcial: 23 de 118 páginas terminadas. 95 pendientes.`

## Contras y riesgos, honestos

**1. El costo de modelo se multiplica por pasada.** Es el riesgo más serio y va directo
contra el objetivo de "varias pasadas cortas". Hoy `_apply_component_families` y el PRD
recorren todo el grafo acumulado en cada corrida, así que la pasada 5 vuelve a narrar lo
de las pasadas 1-4. Cinco pasadas cortas cuestan bastante más que una larga.

El caché de catálogos por página lo mitiga en su mayor parte. Las familias no, por lo
explicado arriba. **Hay que medirlo antes de prometer que las pasadas cortas salen
baratas.**

**2. El grafo crece monótono, los documentos no son comparables entre sí.** El PRD de la
pasada 3 no es "el PRD de las páginas nuevas", es el PRD de todo lo acumulado. Está
bien, pero si la expectativa es "ver qué agregó esta pasada", eso es otra cosa y hay que
construirla aparte (un diff entre corridas).

**3. `get_pending` no cubre lo que nunca se descubrió.** Es completo respecto de lo
*visto* — todo link y toda navegación crean su nodo `Pending`. Pero una URL que sólo
aparece detrás de un click que todavía no se hizo no existe todavía. Es correcto, no es
un bug, pero significa que la to-do list crece a medida que se explora: no esperes que
el total de la primera pasada sea el total real.

**4. No arregla §5.** Si una sola página no termina nunca, el presupuesto por `minutes`
te devuelve la terminal, pero esa página va a volver a colgarse en la pasada siguiente,
y en la siguiente. El corte lo hace **soportable y visible**, no lo cura. La cura es
elegir un backstop (ver el §5 del diagnóstico), y es una conversación con Ezequiel
porque él sacó el techo por página a propósito.

**5. Bug abierto que anula todo esto.** Mientras siga el §3 del diagnóstico —
`config.py:111` lee `config/pragma.yaml` y el wizard escribe `pragma.yaml` — cualquier
presupuesto que configures en el YAML se ignora en silencio. Esto va **antes** que todo
lo demás y es una línea.

## Orden de trabajo

| # | Qué | Estado |
|---|---|---|
| 0 | Arreglar la ruta del config (§3 del diagnóstico) | **hecho** |
| 0b | Avisar de claves YAML desconocidas | **hecho** |
| 1 | Scope en el sink: los links externos dejan de ser `Pending` | **hecho** |
| 1b | A′ de `plan-progreso-en-terminal.md` | **hecho** |
| 2 | Cablear el resume: `crawl_site` siembra con `get_pending()` | **hecho** |
| 3 | `crawl_budget` con default `null`, corte en borde de página | **hecho** |
| 4 | Contador de `route_shape` que sobrevive entre corridas (§1b-b) | **hecho** |
| 5 | Orden de descubrimiento estable (§1b-c) | **pendiente** — ver abajo |
| 6 | Marcar documentos parciales | **hecho** |
| 7a | Cachear propósitos de familia por firma | **hecho** |
| 7b | Cachear catálogos de página por `page_url` | **pendiente** — ver abajo |
| 8 | Elegir backstop para §5 del diagnóstico | pendiente, conversación con Ezequiel |

### Lo que quedó pendiente, y por qué

**Paso 5 — orden de descubrimiento estable.** Una corrida larga visita en el orden de
la cola viva (BFS desde la semilla); una reanudada, en el de `get_pending()`, que es
alfabético. Con el cap de forma de ruta puesto, el orden decide qué URL de cada forma
sobrevive.

No está hecho porque requiere un campo nuevo en el nodo `Page` (número de secuencia),
en los dos backends y en la interfaz, más el orden en `get_pending`. Es un cambio de
esquema, y hacerlo a medias es peor que no hacerlo. El paso 4 —que sí está— cubre la
parte que rompía la equivalencia de forma observable: sin él, varias cortas
**muestreaban más páginas** que una larga. Sin el 5, muestrean la misma cantidad pero
pueden elegir instancias distintas de una misma forma de ruta.

**Paso 7b — caché de catálogos de página.** Es la porción más grande del costo (una
llamada por página contra una por familia). No está hecho porque, a diferencia de los
propósitos de familia, **no hay dónde guardarlo**: `ComponentFamily.purpose` ya era un
campo persistido que se podía releer, y para la narración por página no existe ningún
campo equivalente en la interfaz `GraphStore`. Necesita un slot de storage primero.

Los pasos 2 y 3 son separables: el 2 solo ya da valor (reanudar tras un corte manual),
y el 3 sin el 2 sería un corte sin retorno.

**4 y 5 son los que compran la equivalencia.** Sin ellos el corte funciona igual, pero
varias cortas y una larga dan grafos distintos, y entonces la elección deja de ser
operativa y pasa a ser semántica — que es justo lo que no queremos.

## Lo que este plan no propone

- **No tocar el clustering de familias.** Se rehace entero y eso está bien; ver la
  pregunta 2.
- **No persistir la cola de URLs en disco.** El grafo ya es la cola, vía `Pending`. Una
  segunda fuente de verdad para lo mismo se desincroniza sola.
- **No hacer que `incremental` sea el default.** El comportamiento de hoy tiene que
  seguir siendo lo que pasa si no configurás nada.

## Pipeline de calidad

Aplica `CLAUDE.md`: `python-clean-code` mientras se escribe, `clean-code-principles`
antes del diff — el paso 3 es el único con decisiones de diseño reales (dónde vive el
presupuesto, quién lo consulta) — y `anti-slop` sobre los mensajes de corte y el banner
de documento parcial, que son prosa que ve un usuario.
