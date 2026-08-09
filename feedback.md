- Graph store para guardar iteraciones tipo Neo4J
    - ✅ hecho (`graph_store: neo4j`, `src/storage/neo4j_graph_store.py`)
- Estaría bueno poder visualizar los grafos (podemos hacer cáculo de complejidad de grafos)
    - Parcial: `GraphStore.get_incoming_link_counts` ya calcula grado de entrada por página (se usa
      para priorizar qué explorar primero - ver docs/explicativos/arquitectura.md). Falta el paso
      de visualización en sí (un reporte/heatmap aparte) y cualquier cálculo de complejidad más
      fino (ej. PageRank real vía Neo4j GDS) - ver docs/explicativos/pendientes-futuras-fases.md.
- Cual es la condición de corte del grafo 
    - Chequeo de loops
    - Iteraciones maximas
    - ✅ hecho: `_track_oscillation`/`_skip_repeated_target` (loops), `_apply_diminishing_returns`/
      `max_stalled_finish_attempts` (páginas que no convergen), `max_iterations`/`skeleton_fraction`
      (presupuesto y esqueleto antes de profundidad) - ver docs/explicativos/arquitectura.md.
- Que no haga mutaciones, que no cambie el estado
    - Que tenga safe mode y unsafe mode. Uno con estado y otro sin: para poder mandar, por ejemplo, en modo get.
    - También puede hacer boundaries de mutación, que por ejemplo si hay que inscribirse a una materia y detecta que es un post, marque que no hace la operación pero que hay una operación ahí.
    - ✅ hecho: `safe_mode` (default true) en `SimplePRDGenerator`/`PragmaConfig`, `--unsafe` para
      desactivarlo. Detecta formularios que mandan por POST o texto con verbo de negocio
      (comprar/eliminar/confirmar/...), bloquea el click/submit sin ejecutarlo, y lo deja anotado
      como "mutation boundary" en el PRD final. Ver docs/explicativos/arquitectura.md#modo-seguro-safe-mode.
      Es una heurística, no perfecta - ver docs/explicativos/pendientes-futuras-fases.md.
- Interceptar el javascript que le llega, sacar información de eso.
    - Sigue sin hacerse. Relacionado, pero no lo mismo: el modo seguro (arriba) infiere si una
      acción es una mutación a partir de atributos del DOM (`form.method`, texto del botón), no
      interceptando/leyendo las llamadas de red o el JS que la página realmente ejecuta. Interceptar
      tráfico real (ej. via `page.route()`/`page.on('request')` de Playwright) daría una señal mucho
      más precisa de qué es un GET/POST real y qué manda cada request, en vez de inferirlo del DOM.

- Login / credenciales: dado un sitio con login, poder pasarle credenciales (por variable de
  entorno o flag, nunca en texto plano en `pragma.yaml`) y que la corrida entre a la cuenta antes
  de empezar a explorar, para poder mapear también las pantallas autenticadas. Se cruza directo con
  el modo seguro de arriba: una vez logueado, el crawler se topa con muchas más acciones que sí
  mutan estado (comprar, eliminar, confirmar inscripción) - con `safe_mode` ya implementado, esto
  es más seguro de agregar de lo que hubiera sido antes.
    - ✅ Parcial: `python3 src/cli.py login <url>` + `storage_state_path` ya permiten loguearse una
      vez a mano y reusar esa sesión en corridas posteriores (`PlaywrightScraper` opcional, sin
      romper nada para sitios que no necesitan login). Ver
      docs/explicativos/playwright.md#sesión-persistente--login-storage_state. Falta la parte de
      "pasarle credenciales y que loguee solo" (usuario/contraseña automático) - sigue siendo
      manual, un login por vez, a mano.
