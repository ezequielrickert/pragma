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

Sí, y conviene que sea **una decisión explícita y única**, no la suma de tres flags que
hay que acordarse de combinar.

Propuesta: un modo, con el default siendo exactamente lo de hoy.

```yaml
crawl_mode: one_shot     # one_shot (default) | incremental
crawl_budget:            # sólo se lee en incremental
  pages: 40              # páginas terminadas
  nodes: 500             # nodos creados en el grafo
  minutes: 30            # tiempo de pared
```

- `one_shot` — el comportamiento actual, sin cambios: correr hasta agotar la frontera.
  Quien hoy corre sin tocar nada sigue igual.
- `incremental` — sembrar desde `get_pending()`, cortar en **el primero** de los tres
  presupuestos que se alcance, siempre en borde de página, generar documentos parciales
  y dejar el resto `Pending` para la próxima.

**Por qué los tres presupuestos y no uno**: miden cosas distintas y ninguno cubre solo.
`pages` es el más intuitivo. `nodes` es el que te importaba a vos, el peso de Neo4j.
`minutes` es el único que garantiza que vuelvas a la terminal — porque una sola página
patológica (§5) puede colgarse para siempre sin terminar una página ni crear un nodo,
y ahí los otros dos no te salvan.

**Por qué un modo explícito y no inferirlo** de si hay presupuesto configurado: porque
`fresh: true` es el default y purga el grafo. Un usuario que pone un presupuesto y se
olvida de `--no-fresh` borraría en cada corrida la to-do list que venía a continuar, en
silencio. Con un modo explícito, `incremental` implica `fresh: false` y el conflicto se
resuelve en un solo lugar. Si alguien pide `incremental` **y** `fresh: true` a la vez,
eso es un error de configuración y hay que decirlo al arrancar, no obedecerlo.

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

**Recomendación**: cachear catálogos de página por `page_url`, y **no** cachear familias.
Re-narrar familias en cada corte es el precio correcto de tener el clustering bien.

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

| # | Qué | Por qué en este lugar |
|---|---|---|
| 0 | Arreglar la ruta del config (§3 del diagnóstico) | sin esto nada de lo que sigue se puede configurar |
| 1 | A′ de `plan-progreso-en-terminal.md` | hay que poder *ver* el crawl antes de cambiarle el corte |
| 2 | Cablear el resume: `crawl_site` siembra con `get_pending()` | pieza más grande, casi toda existe |
| 3 | `crawl_mode` + `crawl_budget`, corte en borde de página | el corte propiamente dicho |
| 4 | Marcar documentos parciales | sin esto los documentos mienten por omisión |
| 5 | Cachear catálogos de página por `page_url` | recién acá, con el costo real medido |
| 6 | Elegir backstop para §5 | conversación con Ezequiel, no fix |

Los pasos 2 y 3 son separables: el 2 solo ya da valor (reanudar tras un corte manual),
y el 3 sin el 2 sería un corte sin retorno.

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
