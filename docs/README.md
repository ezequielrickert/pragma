# `docs/` — documentos de salida generados

Esta carpeta es el `out_dir` por defecto de una corrida (`pragma.yaml`'s `out_dir`, `--out`). Todo
lo que hay acá lo escribe `Engine._run_async` (`src/core/engine.py`) al terminar un crawl — nada
se edita a mano.

## Qué archivo es cada cosa

- **`{slug}_prd_{timestamp}.md`** — el Digital Blueprint en prosa (`GraphPRDSynthesizer`).
- **`{slug}_tree_{timestamp}.md`** — el árbol de componentes determinístico, sin IA
  (`component_tree.py`).
- **`{slug}_graph_{timestamp}.json`** — export estructurado del grafo completo (páginas, edges,
  ledger de componentes, texto estático) — solo se genera si se corrió con `--export-json` /
  `export_json: true` (`src/generators/graph_export.py`). Pensado para que otra herramienta lo
  consuma, no para leerlo a mano.
- **`runs.json`** — manifiesto de todas las corridas de todos los sitios (`{site: [entries]}`,
  más reciente al final de cada lista) — se escribe siempre, en cada corrida, independientemente de
  qué otros archivos se hayan generado. Es la forma de responder "¿cuál fue la última corrida de
  este sitio?" sin tener que parsear nombres de archivo (`src/utils/io.py::record_run_manifest`/
  `get_latest_run`).
- **`explicativos/`** — no es salida de una corrida, es documentación del proyecto en sí (ver
  [`explicativos/README.md`](explicativos/README.md)).

## Retención

Nada acá se borra automáticamente — cada corrida agrega archivos nuevos (el timestamp en el
nombre nunca colisiona). Ver
[`explicativos/plan-almacenamiento.md`](explicativos/plan-almacenamiento.md) para el estado de esa
limitación (a diferencia de `debug_logs/`, que sí tiene retención opt-in vía
`debug_logs_keep_last`, `docs/` todavía no).
