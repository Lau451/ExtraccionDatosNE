# Arquitectura — Imports

## Dependencias hacia Core

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 5 endpoints (`router.py:3`). |
| `get_service_client` | `core/database.py` | Único cliente Supabase usado por este módulo — resuelto internamente por los 5 wrappers `*_para_endpoint` de `service.py` (`service.py:7`). Ningún endpoint usa `get_user_client`/RLS. |
| `get_settings` | `core/config.py` | Resuelve `usuario_sistema_id` en `_usuario_sistema_id()` (`service.py:6`, `:21-22`). |
| `ValidationError` | `core/exceptions.py` | Única excepción de dominio levantada por este módulo, en las 5 validaciones de "lista vacía" (`service.py:8`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.

## El acoplamiento inverso: `DEPOSITO_SENTINEL` definido acá, consumido por Catálogo

`imports/service.py:18` define:

```python
DEPOSITO_SENTINEL = "unico"
```

Este módulo la usa en `importar_stock` (`service.py:169`) para normalizar filas de
stock sin depósito explícito antes del upsert:

```python
"deposito": s.deposito if s.deposito else DEPOSITO_SENTINEL,
```

`catalogo/repository.py:6` la importa directo:

```python
from services.presupuestacion.imports.service import DEPOSITO_SENTINEL
```

y la reusa en dos puntos — `repository.py:173` (`buscar_stock_por_deposito`) y
`service.py:247` (`ajustar_stock`, accedido vía el módulo `repo` reexportado) — ya
confirmado en [`../catalogo/arquitectura.md`](../catalogo/arquitectura.md) y
[`../catalogo/decisiones.md`](../catalogo/decisiones.md) D-CATALOGO-004.

**Confirmado desde este lado**: es un acoplamiento negocio→soporte poco común en la
dirección — `imports/` es el módulo de carga masiva (soporte operativo), y
`stock_productos` es una tabla que documentalmente pertenece a `catalogo/` (módulo de
negocio). Que el valor "canónico" para depósito no especificado viva en el módulo de
soporte, y que el módulo de negocio dependa de él, invierte la relación de dependencia
esperada. Si este archivo (`imports/service.py`) se elimina o se renombra la constante,
`catalogo/repository.py` falla en tiempo de import — un error que no apunta a ningún
problema evidente en `catalogo/`. No hay comentario en ninguno de los dos archivos que
explique la decisión — motivo pendiente de definición funcional. Ver D-IMPORTS-004 en
[`decisiones.md`](./decisiones.md).

## La duplicación real: `importar_costos` reimplementa `catalogo.crear_costo`

`imports/service.py:87-144` (`importar_costos`):

```python
if vigente is None:
    repo.crear_costo(client, {..., "fecha_hasta": None, "origen": "import_sistema"})
    nuevos += 1
elif Decimal(str(vigente["costo_unitario"])) != fila.costo_unitario:
    fecha_cierre = fila.fecha_desde - timedelta(days=1)
    repo.cerrar_costo_vigente(client, costo_id=vigente["id"], fecha_hasta=fecha_cierre.isoformat())
    repo.crear_costo(client, {..., "fecha_hasta": None, "origen": "import_sistema"})
    actualizados += 1
else:
    sin_cambios += 1
```

(`service.py:106-137`, condensado). `catalogo/service.py:195-218`
(`crear_costo`, ya documentado como RN-CATALOGO-005/006 en
[`../catalogo/reglas.md`](../catalogo/reglas.md)) implementa el **mismo algoritmo
exacto** sobre la misma tabla `costos_productos`: si el valor no cambió, no escribe
nada; si cambió, cierra el vigente con `fecha_hasta = fecha_desde - 1 día` e inserta uno
nuevo con `fecha_hasta=None`. La única diferencia de dato entre ambas implementaciones
es el campo `origen`: `"import_sistema"` acá (`service.py:115`, `:132`) contra
`"manual"` en Catálogo (`catalogo/service.py:216`, RN-CATALOGO-007).

**Confirmado desde este lado, con evidencia exacta de ambos archivos**: las dos
implementaciones no comparten ninguna función ni constante — cada una arma su propio
dict de la fila `costos_productos` y llama a su propio `repo.crear_costo`/`repo.cerrar_costo_vigente`
(nombres de función iguales por coincidencia de estilo, pero definidos por separado en
`imports/repository.py:79-84` y `catalogo/repository.py`, sin relación de código). Si la
regla de negocio cambiara (por ejemplo, el criterio de cierre de `fecha_hasta`, o
agregar una validación de fecha futura), habría que modificar los dos archivos de forma
consistente, sin que exista un punto único de verdad. Ver D-IMPORTS-003 en
[`decisiones.md`](./decisiones.md) y [`pendientes.md`](./pendientes.md) P1.

## Los 5 flujos de reconciliación: no son homogéneos

El descubrimiento previo del proyecto describía "5 flujos de reconciliación
independientes, cada uno con su propia lógica de nuevos/actualizados/desactivados".
**Confirmado con matices tras leer los 5 algoritmos completos**: solo 3 de los 5 siguen
ese patrón de reconciliación completa por lote (desactivar lo no presente); los otros 2
no tienen concepto de "desactivado" en absoluto.

| Flujo | Nuevo | Actualizado | Desactivado / no presente en el lote |
|---|---|---|---|
| **Productos** (`importar_productos`, `service.py:27-73`) | `INSERT` si `codigo_interno` no existe | `UPSERT` si existe (`on_conflict="drogueria_id,codigo_interno"`) | `activos - set(codigos_del_lote)` → `UPDATE activo=False` (`service.py:62-67`) |
| **Proveedores** (`importar_proveedores`, `service.py:188-244`) | `INSERT` si no tiene `codigo_interno` o si tiene uno que no existe | `UPSERT` si existe | Igual patrón que productos, pero **solo alcanza a proveedores con `codigo_interno`** (ver más abajo) |
| **Clientes** (`importar_clientes`, `service.py:259-325`) | `INSERT` si `codigo_interno` no existe (requiere `nombre` y `tipo`) | `UPDATE` parcial si existe | Igual patrón, pero el `UPDATE` **no reactiva** un cliente ya desactivado (ver más abajo) |
| **Costos** (`importar_costos`, `service.py:87-144`) | `INSERT` si no hay costo vigente para el producto | Versionado temporal (cierra + inserta) si el valor difiere | **No existe el concepto.** Un costo cuyo `codigo_interno` no viene en el lote simplemente no se toca — sigue vigente indefinidamente. |
| **Stock** (`importar_stock`, `service.py:155-183`) | — | `UPSERT` puro por `(producto_id, deposito)`, siempre | **No existe el concepto.** Una fila de `stock_productos` no incluida en el lote conserva su último valor para siempre — no hay lectura de "filas activas" ni desactivación. |

### Matiz 1 — Proveedores sin `codigo_interno` quedan fuera de la reconciliación

`repo.codigos_activos_proveedores` (`repository.py:111-121`) filtra explícitamente
`.not_.is_("codigo_interno", None)` — un proveedor sin código interno nunca entra al
conjunto `activos`, y por lo tanto nunca puede aparecer en `faltantes` ni ser
desactivado por este flujo. Además, `importar_proveedores` inserta **siempre** como
nuevo cualquier fila `sin_codigo` (`service.py:225-226`), sin ningún chequeo de
duplicado — confirmado por el test
`test_importar_proveedores_sin_codigo_interno_siempre_inserta_nuevo`
(`tests/imports/test_service.py:424-449`), que verifica que dos filas sin código
generan dos proveedores nuevos. Reimportar el mismo lote de proveedores sin código dos
veces crea filas duplicadas. Ver RN-IMPORTS-008 en [`reglas.md`](./reglas.md).

### Matiz 2 — Clientes desactivados no se reactivan al reaparecer en un lote posterior

`repo.mapear_clientes_por_codigo` (`repository.py:143-155`) — usado para poblar
`existentes` en `importar_clientes` (`service.py:266`) — **no filtra por `activo` ni
por `deleted_at`**: encuentra clientes inactivos igual que activos. El bloque de
actualización (`service.py:284-291`) arma `campos` a partir de `campos_opcionales` más
`nombre`/`tipo` condicionales y `updated_by` — **sin incluir la clave `"activo"` en
ningún caso**:

```python
if c.codigo_interno in existentes:
    campos = dict(campos_opcionales)
    if c.nombre is not None:
        campos["nombre"] = c.nombre
    if c.tipo is not None:
        campos["tipo"] = c.tipo
    campos["updated_by"] = usuario_id
    repo.actualizar_cliente(client, cliente_id=existentes[c.codigo_interno], campos=campos)
```

(`service.py:284-291`). Comparado con **productos** y **proveedores**, cuyo dict base
(`base`/`_base`, `service.py:39-53` y `:200-214`) incluye `"activo": True`
**incondicionalmente**, tanto para la rama de alta como para la de actualización — un
producto o proveedor previamente desactivado que reaparece en un lote posterior se
reactiva automáticamente. Un cliente en la misma situación **no**: una vez que
`desactivar_clientes` lo marca `activo=False`, ningún import posterior lo vuelve a
poner en `True`, porque la rama de actualización de `importar_clientes` nunca escribe
esa clave. Esta asimetría entre los 3 flujos con reconciliación no está documentada en
el código ni tiene test que la ejercite en `tests/imports/test_service.py` — ver
RN-IMPORTS-007 en [`reglas.md`](./reglas.md) y [`pendientes.md`](./pendientes.md) P2.

## `usuario_sistema_id`: de dónde sale y por qué es fijo

```python
def _usuario_sistema_id() -> str:
    return get_settings().usuario_sistema_id
```

(`service.py:21-22`). `usuario_sistema_id` es un campo **requerido** (sin default) de
`Settings` en `core/config.py:15` — cargado desde `.env` vía
`pydantic_settings.BaseSettings` (`core/config.py:9-16`), memoizado con
`@lru_cache` en `get_settings()` (`core/config.py:23-25`). Es el mismo mecanismo de
configuración que documenta [`../core/`](../core/) para el resto del backend — no hay
un `usuario_sistema_id` distinto o local a este módulo.

Los 5 wrappers `*_para_endpoint` (`service.py:76-82`, `:147-150`, `:180-183`,
`:246-254`, `:327-333`) pasan siempre `usuario_id=_usuario_sistema_id()` — **nunca**
`usuario.id` del `UsuarioPerfil` resuelto por `require_roles` en `router.py`, aunque el
router sí tiene ese dato disponible (lo usa solo para resolver `drogueria_id`, nunca
para `usuario_id`). Es decir: sea cual sea el usuario autenticado que dispare
`POST /imports/productos`, todas las filas creadas o actualizadas por esa llamada
quedan con `created_by`/`updated_by` = el mismo UUID técnico fijo. Ver D-IMPORTS-002 en
[`decisiones.md`](./decisiones.md) y [`pendientes.md`](./pendientes.md) P1.

## Roles de escritura: coincide con Catálogo, difiere del resto

`imports/router.py:26`:

```python
_ROLES_IMPORT = ("admin", "gerencia", "compras")
```

Confirmado por grep de `_ROLES_ESCRITURA`/`_ROLES_LECTURA`/`_ROLES_ELIMINACION` sobre
todo `services/presupuestacion/` en esta sesión: **coincide exactamente** con
`catalogo/router.py:44` (`_ROLES_ESCRITURA_CATALOGO = ("admin", "gerencia",
"compras")`), pero **difiere** de `_ROLES_ESCRITURA` en `clientes/router.py:36`,
`eventos/router.py:33` y `procesos_comerciales/router.py:18` — los tres definen
`("admin", "gerencia", "lider_comercial", "comercial")`, sin `compras` pero con
`lider_comercial`/`comercial`. Es decir: `imports/` sigue el patrón de permisos de
`catalogo/` (el módulo dueño de 4 de las 5 tablas que toca), no el de `clientes/` (dueño
de la quinta) — una asimetría real, dado que `imports/` también puede crear y
desactivar clientes con este único tuple de roles, sin que `lider_comercial` o
`comercial` (que sí pueden hacerlo vía `clientes/router.py:36`) puedan disparar una
importación masiva de clientes. Ver RN-IMPORTS-013 en [`reglas.md`](./reglas.md).

## Diagrama de acoplamiento

```
                    productos / costos_productos / stock_productos /
                    proveedores (dueño: catalogo/)      clientes (dueño: clientes/)
                              │                                │
                    ┌─────────┴─────────┐                      │
                    │                   │                      │
              catalogo/service.py  imports/service.py ─────────┘
              (crear_costo,        (importar_productos, importar_costos,
               ajustar_stock)       importar_stock, importar_proveedores,
                    │                importar_clientes)
                    │                       │
                    └──── DEPOSITO_SENTINEL ┘
                    (definida en imports/service.py:18,
                     importada por catalogo/repository.py:6 — acoplamiento inverso)
```

Ningún import de Python conecta `imports/` con `catalogo/service.py` ni con
`clientes/service.py` para la lógica de negocio — cada uno construye sus propias
queries y su propia versión del algoritmo de costo. La única conexión de código real es
la de `DEPOSITO_SENTINEL`, y va en la dirección catalogo→imports.
