# Base de datos — Comparativas

Todas las operaciones vía `repository.py` usan `supabase-py`. `service.py` recibe el
cliente como parámetro (`client: Client`) en `asignar_proveedor` — es
`get_service_client()` cuando corre desde el endpoint
(`asignar_proveedor_para_endpoint`, `service.py:28-33`), o `service_client` de test
cuando corre desde los tests de integración. `router.py` además usa `user_client`
(RLS-aware, `core.database.get_user_client`) para los 3 endpoints — ver
[`arquitectura.md`](./arquitectura.md).

## `v_renglones_ganados` (vista, no es dueño)

Dueño real del schema: `docs/schema/extractor_final.sql:1576-1595`. Ver
[`arquitectura.md`](./arquitectura.md) para la definición SQL completa.

| Columna expuesta | Origen | Modelo (`RenglonGanado`, `models.py:10-21`) |
|---|---|---|
| `proceso_comercial_id` | `comparativas.proceso_comercial_id` | `str` |
| `proceso` | `procesos_comerciales.nombre` | `str` |
| `cliente` | `clientes.nombre` (`LEFT JOIN`, puede ser `NULL`) | `str \| None` |
| `oferta_item_id` | `ofertas_items.id` | `str` |
| `renglon_id` | `ofertas_items.renglon_id` | `str \| None` |
| `descripcion` | `ofertas_items.descripcion` | `str \| None` |
| `precio_unitario` | `ofertas_items.precio_unitario` | `Decimal` |
| `cantidad_ofertada` | `ofertas_items.cantidad_ofertada` | `Decimal \| None` |
| `ganado_oficial` | `ofertas_items.adjudicada` | `bool` |
| `ganado_estimado` | `ofertas_items.adjudicacion_estimada` | `bool` |
| `nivel` | `CASE` sobre `adjudicada`/`adjudicacion_estimada` | `str \| None` (`"oficial"`, `"estimado"` o `None`) |

**Operación**: `SELECT` — `listar_renglones_ganados` (`repository.py:36-43`), filtrado
por `proceso_comercial_id` (`.eq("proceso_comercial_id", proceso_comercial_id)`), sin
`.limit()` — trae todas las filas que matchean. Llamada directa desde
`router.py:27`, sin pasar por `service.py` (no hay lógica de negocio que aplicar a una
lectura).

## `v_ofertas_sin_matchear` (vista, no es dueño)

Dueño real del schema: `docs/schema/extractor_final.sql:1612-1622`.

| Columna expuesta | Origen | Modelo (`OfertaSinMatchear`, `models.py:24-28`) |
|---|---|---|
| `texto_crudo` | `ofertas_items.proveedor` | `str` |
| `drogueria_id` | `comparativas.drogueria_id` | `str` |
| `apariciones` | `COUNT(*)` agrupado | `int` |
| `veces_ganador` | `COUNT(*) FILTER (WHERE adjudicada)` | `int` |

**Operación**: `SELECT` — `listar_ofertas_sin_matchear` (`repository.py:46-47`), **sin
ningún filtro** (`.select("*").execute()`) — trae todas las filas de todas las
droguerías presentes en la tabla subyacente; el escopeo por droguería del solicitante
lo hace la RLS de `ofertas_items`/`comparativas` vía `security_invoker`, no un `.eq()`
explícito en el código (ver [`arquitectura.md`](./arquitectura.md)). Llamada directa
desde `router.py:35`.

## `ofertas_items` (no es dueño — lee y actualiza 1 columna)

Dueño real: módulo `extraccion/` (documentado como "Extracción-Validación", ver
[`../extraccion_validacion/base_de_datos.md`](../extraccion_validacion/base_de_datos.md)
para el `INSERT` completo). Este módulo solo la lee puntualmente y actualiza
`proveedor_id`.

| Columna | Uso en este módulo |
|---|---|
| `id` | Clave de búsqueda (`buscar_oferta_item`, `repository.py:6-10`; `.eq("id", oferta_item_id)`, también en `router.py:48`). |
| `drogueria_id` | Leída para comparar contra `proveedores.drogueria_id` (`service.py:20-21`, RN-COMPARATIVAS-001) y contra `usuario.drogueria_id` (`router.py:55-56`, RN-COMPARATIVAS-002). **No se escribe** desde este módulo. |
| `proveedor_id` | **Única columna que este módulo escribe** (`actualizar_oferta_item`, `campos={"proveedor_id": proveedor_id}`, `service.py:24`). |
| `es_drogueria_propia` | **No se lee ni se escribe en ningún punto de este módulo** — ver [`arquitectura.md`](./arquitectura.md) hallazgo cruzado y [`pendientes.md`](./pendientes.md). |

**Operaciones**:
- `SELECT *` — `buscar_oferta_item` (`repository.py:6-10`, por `id`, `.limit(1)`).
- `SELECT id, drogueria_id` — inline en `router.py:45-51` (verificación de tenant
  previa al `POST`, no pasa por `repository.py`).
- `UPDATE` — `actualizar_oferta_item` (`repository.py:24-33`), genérica (recibe
  `campos: dict[str, Any]` — la firma admite actualizar cualquier columna, pero
  `service.py:24` siempre le pasa `{"proveedor_id": proveedor_id}`, la única
  invocación real en todo el módulo).

## `proveedores` (no es dueño — solo lector)

Dueño real: módulo `catalogo/` (no confirmado en esta sesión — fuera de alcance).

| Columna | Uso en este módulo |
|---|---|
| `id, drogueria_id` | `SELECT` puntual por `id` (`buscar_proveedor`, `repository.py:13-21`, `.limit(1)`), usado para validar que el proveedor exista y pertenezca a la misma droguería que la oferta (RN-COMPARATIVAS-001). |

**Operaciones**: solo `SELECT`, columnas acotadas explícitamente
(`.select("id, drogueria_id")`, `repository.py:16`) — no trae `razon_social` ni ninguna
otra columna, porque este módulo no necesita mostrar datos del proveedor, solo validar
su existencia y tenant.

## Tablas que este módulo NO toca

`comparativas` — se lee indirectamente a través de los `JOIN`/`GROUP BY` de ambas
vistas, pero ningún archivo de este módulo hace `client.table("comparativas")`
directamente. `historial_cambios` — cero escrituras, ver
[`pendientes.md`](./pendientes.md).
