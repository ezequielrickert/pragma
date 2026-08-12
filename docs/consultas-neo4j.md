# Consultas guardadas

Nadie lee un grafo de 5000 nodos entero. Se leen subgrafos, y estas son las
preguntas que valen la pena hacerle a un crawl.

Antes de empezar, cargá los estilos una vez: abrí `http://localhost:7474` y
arrastrá `scripts/neo4j-browser.grass` sobre la ventana del browser. Sin eso,
Neo4j elige solo qué propiedad mostrar como etiqueta y termina mostrando el
path CSS, que es lo más largo y lo menos legible que tiene un componente.

En todas las consultas, reemplazá `$site` por el dominio que crawleaste
(`'empanad.app'`, por ejemplo).

## Panorama: qué se descubrió

```cypher
MATCH (n {site: $site})
RETURN labels(n) AS tipo, count(*) AS cantidad
ORDER BY cantidad DESC
```

## Una pantalla completa

Todo lo que hay en una página, dos saltos a la redonda. Es la consulta que
más se usa: en vez de abrir el grafo entero, se abre una pantalla.

```cypher
MATCH (p:Page {site: $site, url: $url})
OPTIONAL MATCH (p)-[:HAS_COMPONENT]->(c:Component)
OPTIONAL MATCH (c)-[:TRIGGERS]->(r:Request)
RETURN p, c, r
```

## Qué hace cada control de una página

Sin abrir ninguna propiedad JSON: la acción está en la arista.

```cypher
MATCH (c:Component {site: $site, page_url: $url})-[i:INTERACTED]->(destino:Page)
RETURN c.caption AS control, i.action AS accion, i.value AS valor,
       i.navigated AS navego, destino.caption AS termina_en
ORDER BY c.caption, i.seq
```

## El flujo entre pantallas

```cypher
MATCH (a:Page {site: $site})-[n:NAVIGATED_TO]->(b:Page)
RETURN a.caption AS desde, n.component AS disparador, b.caption AS hacia
ORDER BY desde
```

## Todos los endpoints, y quién los llama

```cypher
MATCH (rf:RequestFamily {site: $site})-[:HAS_REQUEST]->(r:Request)
OPTIONAL MATCH (c:Component)-[:TRIGGERS]->(r)
RETURN rf.method AS metodo, r.endpoint AS endpoint,
       collect(DISTINCT c.caption) AS lo_disparan
ORDER BY metodo, endpoint
```

## Peticiones que fallaron

Los códigos de estado viven en `network_requests` del componente, todavía
como JSON — se resuelve en la Fase 2 del plan, junto con la latencia.

```cypher
MATCH (c:Component {site: $site})
WHERE any(req IN c.network_requests WHERE req CONTAINS '"failed": true')
RETURN c.page_url AS pagina, c.caption AS control, c.network_requests AS crudo
```

## Componentes sin nombre accesible

El insumo de la auditoría de accesibilidad (Fase 5c). Un control sin texto
visible ni label es un control que un lector de pantalla no puede anunciar.

```cypher
MATCH (c:Component {site: $site})
WHERE c.text = '' AND c.label = '' AND c.layer = 'semantic'
RETURN c.page_url AS pagina, c.tag AS etiqueta, c.path AS ruta
ORDER BY pagina
```

## Lo que quedó sin explorar

Los mismos números del reporte de cobertura, pero navegables.

```cypher
MATCH (c:Component {site: $site, interacted: false})
WHERE c.layer = 'semantic'
RETURN c.page_url AS pagina, count(*) AS sin_explorar
ORDER BY sin_explorar DESC
```

## Qué dedujo el modelo, separado de lo que se vio

Todo nodo inferido lleva la etiqueta `:Inferred`. Esta es la consulta que
permite auditar una deducción hasta la evidencia que la originó.

```cypher
MATCH (f:ComponentFamily:Inferred {site: $site})-[:HAS_VARIANT]->(c:Component)
RETURN f.caption AS familia, f.purpose AS proposito,
       collect(c.caption)[0..5] AS ejemplos, f.member_count AS miembros
ORDER BY miembros DESC
```

## Familias de componentes con estilos distintos

Adelanto de la regla de consistencia de la Fase 5a: miembros de una misma
familia que no comparten color de fondo son una inconsistencia visual.

```cypher
MATCH (f:ComponentFamily:Inferred {site: $site})-[:HAS_VARIANT]->(c:Component)
WITH f, collect(DISTINCT c.background_color) AS colores
WHERE size(colores) > 1
RETURN f.caption AS familia, colores
ORDER BY size(colores) DESC
```
