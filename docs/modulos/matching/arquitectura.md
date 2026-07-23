# Arquitectura — Matching

## Dependencias hacia Core

Matching no importa de ningún otro módulo de negocio de `presupuestacion/` para su
lógica de dominio; depende de Core para eso.

| Import | Origen | Uso |
|---|---|---|
| `get_service_client` | `core/database.py` | Resuelto internamente por los 2 wrappers `*_para_endpoint` de `service.py` (`service.py:7,221,229`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en los 3 endpoints de `router.py` (`router.py:5`). |
| `NotFoundError` | `core/exceptions.py` | Levantada cuando `confirmar_matching`/`marcar_sin_match` no encuentran el `item_proceso` (`service.py:8,149,196`). |
| `ForbiddenError` | `core/exceptions.py` | Levantada por `router.py` cuando el renglón no pertenece a la droguería del usuario (`router.py:6,37`). |
| `normalizar_descripcion` | `core/texto.py` | Normaliza la descripción libre del renglón antes de comparar/matchear (`service.py:9,43`). Uno de los 2 únicos consumidores de `core/texto.py` en todo `presupuestacion/` (el otro es `extraccion/service.py`, ver [`../core/README.md`](../core/README.md)). |
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 3 endpoints (`router.py:4,44,56,65`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.

## Acoplamiento de tabla con `catalogo/` — lectura directa de `productos`

`matching/repository.py:40-49` (`listar_productos_activos`) hace:

```python
def listar_productos_activos(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]:
    resultado = (
        client.table("productos")
        .select("id, nombre")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)
        .is_("deleted_at", None)
        .execute()
    )
    return resultado.data
```

Es un `SELECT` directo contra `productos`, sin pasar por `catalogo/repository.py` ni
`catalogo/service.py`. Este acoplamiento ya está documentado desde el lado de
Catálogo en
[`../catalogo/arquitectura.md`](../catalogo/arquitectura.md#matchingrepositorypy--lectura-de-productos)
— Matching es uno de 5 módulos que leen o escriben directo sobre las tablas de
Catálogo sin pasar por su código. A diferencia de `imports/repository.py` (CRUD
masivo) o `pricing/repository.py` (reimplementa una regla de vigencia), Matching solo
hace un `SELECT` de solo lectura sobre `id, nombre` — el acoplamiento es de menor
riesgo que los otros documentados en esa página, pero sigue siendo el mismo patrón
estructural: cada módulo construye su propia query Supabase contra una tabla que no
es de su propiedad.

## El flujo alias-primero-luego-fuzzy

`procesar_matching_item` (`service.py:39-110`) es el punto de entrada del matching
automático. Su estructura es una cascada de dos estrategias, evaluadas en orden fijo:

1. **Alias del cliente** (`service.py:45-69`): si se pasó un `cliente_id`, busca un
   alias vigente (`repo.buscar_alias_vigente`, filtro
   `cliente_id + descripcion_normalizada + vigente=True`, `repository.py:25-37`). Si
   existe, el matching es automático — **no se ejecuta ningún scoring**, no se
   generan candidatos, el renglón queda `producto_id`/`alias_id` fijados y
   `estado_matching="automatico"`. El alias se marca como reusado
   (`marcar_alias_usado`, incrementa `veces_usado`, `repository.py:52-58`).
2. **Fuzzy matching** (`service.py:71-73`, solo si no hubo alias o no se pasó
   `cliente_id`): `_generar_candidatos` (`service.py:17-36`) trae **todos** los
   productos activos de la droguería a memoria y corre
   `rapidfuzz.process.extract(..., scorer=fuzz.WRatio, limit=5)` para obtener el
   top-5 por similitud contra `descripcion_normalizada`. Ver riesgo de escalabilidad
   en [`pendientes.md`](./pendientes.md) y umbral/top-K en
   [`reglas.md`](./reglas.md).

El resultado de la cascada decide `estado_matching`: `automatico` (paso 1),
`sugerido`/`pendiente` (paso 2, según el umbral) — nunca ambos caminos a la vez. Ver
[`flujo.md`](./flujo.md) para el detalle paso a paso y
[`estados.md`](./estados.md) para la máquina de estados completa.

## Quién importa este módulo

Grep de `"matching"` sobre `services/presupuestacion/` (excluyendo el propio
directorio `matching/`) encuentra un único importador de código:
`extraccion/service.py:15`
(`from services.presupuestacion.matching.service import procesar_matching_item`),
llamado en `extraccion/service.py:88-91` por cada `item_proceso` que
`_materializar_licitacion` crea. Ningún otro módulo de negocio importa
`matching.service`, `matching.repository` ni `matching.models`. Ver
[`README.md`](./README.md) y
[`../extraccion_validacion/arquitectura.md`](../extraccion_validacion/arquitectura.md#dependencia-hacia-matching)
para el mismo acoplamiento documentado desde el lado consumidor.

## Patrón `service_client` / `user_client`

Igual que `pricing/`, `extraccion/` y `presupuestos/`, el router de este módulo nunca
importa el cliente de servicio directamente. `confirmar_matching_para_endpoint`
(`service.py:214-225`) y `marcar_sin_match_para_endpoint` (`service.py:228-229`) son
los dos únicos puntos que llaman a `get_service_client()`, con el motivo documentado
en el docstring del primero:

> "Corre con service_role: además de actualizar el item, invalida/crea alias y marca
> el candidato elegido — la RLS de esas tablas no incluye 'superadmin' en
> INSERT/UPDATE, así que igual que en pricing, el router nunca importa el service
> client directamente." (`service.py:217-219`)

Verificado contra `docs/schema/rls_final.sql`: las políticas `alias_ins`/`alias_upd`
(líneas 196-197), `ip_ins`/`ip_upd` (líneas 229-230) y `mc_ins`/`mc_upd` (líneas
236-237) restringen `INSERT`/`UPDATE` a
`get_rol() IN ('admin','gerencia','lider_comercial','comercial')` — `superadmin` está
ausente de esa lista en las tres tablas (solo aparece en las políticas `DELETE`, vía
`es_superadmin()`). El comentario del código es exacto: un usuario `superadmin`
autenticado con `user_client` (RLS-aware) no podría ejecutar los `UPDATE`/`INSERT`
que hace `confirmar_matching`, de ahí la necesidad de `service_client`.

`router.py` sí usa `get_user_client` (`router.py:5,45,57,66`) — pero solo para el
`SELECT` de verificación de pertenencia de droguería en los 2 primeros endpoints
(`_validar_item_de_la_drogueria`, `router.py:22-37`) y para el `SELECT` directo sobre
la vista `v_matching_pendiente` en el tercero (`router.py:68`, que no pasa por
`service.py` en absoluto). Ver [`base_de_datos.md`](./base_de_datos.md) y
[`casos_de_uso.md`](./casos_de_uso.md).

## Validación de tenant duplicada entre módulos (mismo patrón ya documentado)

`_validar_item_de_la_drogueria` (`router.py:22-37`) reimplementa, con su propio
nombre de función y su propia query, el mismo patrón que ya existe en
`clientes/service.py:18` (`_validar_cliente_de_la_drogueria`),
`presupuestos/router.py:24,42` (`_validar_presupuesto_de_la_drogueria`,
`_validar_item_de_la_drogueria` — **mismo nombre de función que en este módulo**,
implementación independiente) y `compras/router.py:26`
(`_validar_oc_de_la_drogueria`). No hay una función compartida en `core/` para este
chequeo — cada router construye su propio `SELECT id, drogueria_id` + comparación
`usuario.rol != "superadmin" and ... != usuario.drogueria_id` +
`ForbiddenError`. Ver [`pendientes.md`](./pendientes.md).
