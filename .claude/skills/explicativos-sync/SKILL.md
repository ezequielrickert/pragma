---
name: explicativos-sync
description: Update ARCHITECTURE.md and/or README.md right after editing core kernel files (Engine/registries/config/CLI/interfaces), adding or changing a document generator, touching dashboard/, or changing a database/ladybug/ mixin or spiders/ module in a way that changes the system's shape. Also use when the user explicitly asks to "actualizar los docs explicativos" or "documentar esto". Do NOT use for changes to generated output (docs/*_prd_*.md, data/output/, runs.json) or for per-module reference docs under docs/dev/ (those are kept in sync by tests/test_dev_docs.py, not this skill) or for wiki/-shaped durable lessons (see wiki-update).
---

# Sincronizar los docs explicativos de alto nivel

`docs/explicativos/` se borró por completo el 2026-08-10 (no quedó parcialmente desactualizado,
dejó de existir) - esta skill apuntaba ahí y quedó igual de muerta hasta que se retargeteó el
2026-08-21. Hoy los dos documentos que describen "cómo funciona esto ahora mismo" a nivel sistema
son `ARCHITECTURE.md` y `README.md`, y ninguno de los dos tiene un test que los mantenga honestos
- a diferencia de `docs/dev/` (una entrada por módulo, sincronizada con `tests/test_dev_docs.py`:
todo `Details:` resuelve a un archivo/heading real, ningún doc describe un módulo borrado). Esta
skill existe para la mitad que ningún test cubre.

## Cuándo dispara

Inmediatamente después de editar cualquiera de estos archivos, en el mismo cambio (no como un
paso separado para "después"):

| Si editaste... | Actualizá... |
|---|---|
| `core/engine.py`, `core/docs_engine.py`, `core/registry.py`, `core/config.py`, `cli.py`, `core/wizard.py` | `ARCHITECTURE.md`'s secciones de Kernel/"Directory Roles", y el párrafo "Design:" de `README.md` si el flujo de alto nivel cambió |
| `generators/*.py` - un generador nuevo, o un cambio al contrato `DocumentGenerator`/`DocumentOutput` | `ARCHITECTURE.md`'s sección "Output Documents" |
| `dashboard/*.py` | `ARCHITECTURE.md`'s sección "The Dashboard" y su bullet `dashboard/` en "Directory Roles" |
| `database/ladybug/*.py` - un mixin nuevo, o un cambio de schema | `ARCHITECTURE.md`'s bullet `database/` en "Directory Roles" |
| `spiders/*.py` - cambios de orquestación del crawl | `ARCHITECTURE.md`'s bullet `spiders/` en "Directory Roles" |
| Un comando CLI nuevo o cambiado (`cli.py`, `core/*_cli.py`) | `STARTUP.md` (el comando en sí, con un comentario corto) y `README.md`'s sección de Setup/run si cambia el flujo que ahí se describe |

## Proceso

1. **Releé la sección concreta del doc que tu cambio afecta** antes de tocarla - necesitás saber
   qué dice hoy para no duplicar contenido ni dejar una frase vieja contradiciendo la nueva.
2. **Editá esa sección in place**, con el mismo nivel de detalle y estilo que el resto del archivo
   (tablas para datos estructurados; prosa densa, con nombres reales de módulos/funciones/ADRs,
   para el "por qué" y el "cómo"). No reescribas el documento entero por un cambio puntual.
3. Si agregaste un paquete nuevo que no encaja en ningún bullet existente de "Directory Roles",
   agregá uno - mismo criterio que usa `wiki-update` para decidir "archivo nuevo vs. sección
   existente".
4. Si el cambio invalida algo que estos docs asumían como cierto (un contrato viejo, un paquete
   que ya no existe), **reemplazá esa sección**, no la dejes al lado de la corrección como si
   ambas siguieran siendo verdad.
5. Corré la skill `anti-slop` sobre la prosa nueva antes de darla por terminada - `CLAUDE.md`'s
   pipeline de calidad la exige también para prosa generada, no solo para código.

## Qué NO hacer

- No toques `ARCHITECTURE.md`/`README.md` por cambios en salida generada (`docs/*_prd_*.md`,
  `data/output/`, `runs.json`) - eso es salida de una corrida, no código.
- No dupliques acá lo que `docs/dev/` ya cubre con test propio - si el cambio es a un módulo
  puntual y ya tiene su `docs/dev/<paquete>/<módulo>.md`, esa es la actualización que corresponde
  (ver el `Details:` docstring del módulo), no una reescritura de `ARCHITECTURE.md`.
- No dupliques acá una lección de dominio general (eso es `wiki/`, ver la skill `wiki-update`).
- No actualices el doc entero "por las dudas" cuando el cambio real es acotado - un diff grande
  por un cambio chico dificulta ver qué cambió realmente la próxima vez.

## Después de actualizar

Decile al usuario qué archivo(s) (`ARCHITECTURE.md`, `README.md`, `STARTUP.md`) se actualizaron y,
en una línea cada uno, qué cambió - no alcanza con decir "actualicé los docs".
