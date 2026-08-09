# Documentos explicativos de Pragma

> **Aviso — migración a crawl4ai (commit `f5f1c02`, rama `scraper`):** el proyecto reemplazó por
> completo el motor que estos documentos describían — el loop de decisión por-paso vía LLM
> (`SimplePRDGenerator`, `PlaywrightScraper`, el servidor REST de `src/api_server/`, `RestScraper`)
> ya no existe, reemplazado por un crawler mecánico basado en `crawl4ai`
> (`MechanicalCrawler`/`Crawl4AICrawler`, ver `src/crawlers/`). La referencia autoritativa y
> actualizada de la arquitectura actual es el **`ARCHITECTURE.md`** de la raíz del repo (en inglés).
> Esta carpeta quedó como documentación de una fase anterior del proyecto — útil para entender
> decisiones y el porqué de ciertos diseños, pero **no asumas que el código citado abajo sigue
> existiendo tal cual** salvo que se indique lo contrario.

Esta carpeta explica, en español y con más detalle pedagógico, cómo funcionaba cada pieza concreta
del proyecto en su versión anterior (el "Ralph-Loop" con decisión por-paso vía LLM), más los
residuos de mejoras que se estaban construyendo sobre esa base cuando la migración a `crawl4ai`
llegó primero.

## Qué queda de esta carpeta, y su estado

| Documento | Explica | Estado |
|---|---|---|
| [`arquitectura.md`](arquitectura.md) | El proyecto de la versión anterior: micro-kernel, registries, config en capas, el CLI, y el Ralph-Loop. | **Desactualizado** — describe `SimplePRDGenerator`/`PlaywrightScraper`, ya no existen. Ver `ARCHITECTURE.md` para la versión vigente. |
| [`neo4j.md`](neo4j.md) | Esquema del grafo (nodos, relaciones, `<id>`/`<elementId>`, identidad de URL). | **Parcialmente vigente** — `Page`/`Component` siguen existiendo en `GraphStore`, pero el esquema sumó campos nuevos (`description`, `title` en `Page`; nodos de texto estático; `network_requests`) y la identidad de URL ahora la resuelve `src/utils/urls.py::clean_url`/`route_shape` (más sofisticado que lo documentado acá — colapsa tokens dinámicos automáticamente). Revisar contra `src/core/interfaces.py::GraphStore` antes de confiar en el detalle. |
| [`pendientes-futuras-fases.md`](pendientes-futuras-fases.md) | Qué quedó afuera de alcance en cada fase de mejora del recorrido/contexto (0-3) sobre la arquitectura anterior. | **Superado** — la mayoría de esos problemas (identidad de URL, condición de corte del loop) los resolvió la migración a `crawl4ai` de otra forma. Ver la nota al pie de ese archivo. |

`playwright.md` y `modulo3-api-server-y-rest-scraper.md` se eliminaron — describían módulos
(`PlaywrightScraper`, `src/api_server/`, `RestScraper`) que ya no existen en absoluto, sin ningún
sucesor directo dentro de esta carpeta todavía.

## Política: mantenerlos al día (vigente para lo que sigue activo)

Si tocás `src/storage/*`/`src/core/interfaces.py::GraphStore`, actualizá `neo4j.md`. El resto de la
política de sync (`.claude/skills/explicativos-sync/SKILL.md`) sigue describiendo archivos que ya
no existen — necesita su propia revisión antes de confiar en ella para el código nuevo
(`src/crawlers/*`).
