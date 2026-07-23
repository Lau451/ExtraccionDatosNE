# Módulo Matching — `services/presupuestacion/matching/`

## Qué es

Matching resuelve a qué producto del catálogo corresponde la descripción libre de un
renglón (`items_proceso.descripcion`) — el texto tal como viene de una licitación,
cotización o extracción IA, sin ningún identificador de producto propio. Expone dos
mecanismos, en orden de prioridad:

1. **Alias vigente del cliente** (`cliente_producto_alias`): si ese cliente ya usó
   antes la misma descripción normalizada y un humano la confirmó, el matching es
   automático, sin scoring.
2. **Fuzzy matching** (`rapidfuzz.fuzz.WRatio`) contra los productos activos de la
   droguería, si no hay alias: genera hasta 5 candidatos y decide `sugerido`
   (confianza ≥ 70) o `pendiente` (confianza < 70, o sin candidatos) según un umbral
   fijo.

El módulo tiene 4 archivos con código: `models.py` (42 líneas), `repository.py` (107
líneas), `service.py` (230 líneas — el más largo, concentra toda la lógica de
matching y confirmación) y `router.py` (70 líneas). `__init__.py` está vacío. Todo
verificado leyendo cada archivo completo en esta sesión.

## Qué NO hace

- **No expone un endpoint para "correr matching".** `procesar_matching_item` no tiene
  ruta HTTP propia — se dispara como efecto colateral desde otro módulo,
  `extraccion.service._materializar_licitacion`, una vez por cada `item_proceso`
  recién creado (`extraccion/service.py:15,88-91`). Confirmado por grep cruzado en
  esta sesión: es el único importador de `matching.service` en todo
  `presupuestacion/`. Ver [`arquitectura.md`](./arquitectura.md).
- **No toca el catálogo directamente salvo lectura.** `matching/repository.py:42`
  (`listar_productos_activos`) hace `SELECT id, nombre FROM productos` — el mismo
  patrón de acoplamiento de tabla (leer `productos` sin pasar por
  `catalogo/repository.py`) que ya documenta
  [`../catalogo/arquitectura.md`](../catalogo/arquitectura.md) para varios módulos.
  Matching nunca crea, actualiza ni borra una fila de `productos`.
- **No gestiona alias de proveedor todavía.** La tabla `proveedor_producto_alias`
  (espejo por proveedor de `cliente_producto_alias`) existe en el schema
  (`docs/schema/extractor_final.sql:956-973`) pero no tiene ningún código propio en
  este módulo — comentario explícito en `repository.py:65-68`. Ver
  [`pendientes.md`](./pendientes.md).
- **No implementa los 4 métodos de matching que declara.** `MetodoMatching`
  (`models.py:7`) admite `"exact" | "fuzzy" | "embedding" | "manual"`, pero el único
  valor que el código de este módulo genera es `"fuzzy"` (`service.py:33`) — no se
  encontró en esta sesión ningún punto de `matching/` que asigne `"exact"`,
  `"embedding"` o `"manual"`. Ver [`reglas.md`](./reglas.md).
- **No reabre un matching ya resuelto.** No existe ninguna función en este módulo que
  vuelva a poner `estado_matching` en `pendiente` desde `confirmado` o `sin_match`.
  Ver [`estados.md`](./estados.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `matching/__init__.py` | Vacío. |
| `matching/models.py` | `EstadoMatching` y `MetodoMatching` (`Literal`), `CandidatoMatching`, `ResultadoMatchingItem` (response de los 3 casos de uso), `ConfirmarMatchingRequest` (body del endpoint de confirmación) e `ItemMatchingPendiente` (fila de la vista `v_matching_pendiente`). |
| `matching/repository.py` | Acceso a datos puro: 10 funciones sobre `items_proceso`, `procesos_comerciales` (solo lectura), `cliente_producto_alias`, `productos` (solo lectura) y `matching_candidatos`. |
| `matching/service.py` | 3 casos de uso públicos (`procesar_matching_item`, `confirmar_matching`, `marcar_sin_match`) más sus wrappers `*_para_endpoint`, y 2 helpers privados (`_generar_candidatos`, `_upsert_alias`). |
| `matching/router.py` | 3 endpoints HTTP: confirmar matching, marcar sin match y listar pendientes. |

## Quién lo consume

- **`extraccion/service.py`** (módulo `extraccion/` dentro de `presupuestacion/`,
  documentado en [`../extraccion_validacion/`](../extraccion_validacion/)):
  `_materializar_licitacion` importa `procesar_matching_item`
  (`extraccion/service.py:15`) y lo llama por cada `item_proceso` que crea
  (`extraccion/service.py:88-91`) — confirmado desde este lado del acoplamiento,
  releyendo `extraccion/service.py` en esta sesión. Es el único consumidor de código
  Python de este módulo encontrado en todo `services/presupuestacion/` (grep de
  `"matching"` sobre el árbol, ver [`arquitectura.md`](./arquitectura.md)).
- **Los 3 endpoints HTTP** (`router.py`) están montados en
  `services/presupuestacion/main.py:19,43`
  (`app.include_router(matching_router, tags=["matching"])`), pero no se encontró en
  esta sesión ningún cliente HTTP dentro del repositorio que los consuma: `grep` de
  `"confirmar-matching"`, `"sin-match"` y `"matching/pendientes"` sobre `frontend/`
  no tuvo resultados. Ver [`casos_de_uso.md`](./casos_de_uso.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, acoplamiento de
  tabla con `catalogo/`, el flujo alias-primero-luego-fuzzy.
- [`base_de_datos.md`](./base_de_datos.md) — tablas tocadas, columnas y CRUD real.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-MATCHING-NNN).
- [`flujo.md`](./flujo.md) — los 3 flujos principales paso a paso.
- [`estados.md`](./estados.md) — la máquina de estados de `estado_matching`.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 3 endpoints, con evidencia de quién
  (no) los consume.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-MATCHING-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.
