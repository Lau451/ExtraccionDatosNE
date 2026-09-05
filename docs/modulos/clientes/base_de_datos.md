# Base de datos — Clientes

> **Actualización (change `terceros-modelo`, Fase 8/10)**: `clientes` perdió
> `nombre`/`direccion`/`ciudad`/`provincia`/`codigo_postal`/`plazo_pago_dias`/
> `condiciones_pago`/`codigo_interno` (movidos a `terceros`,
> `tercero_direcciones`/`condiciones_pago`) y ganó `condicion_pago_id`/`forma_pago_id`
> (FK). `cliente_contactos` **fue eliminada**; reemplazada por `terceros_contactos`
> (compartida con `proveedores`). Ver [`../terceros/base_de_datos.md`](../terceros/base_de_datos.md).
> Las tablas de abajo describen el esquema **anterior** a esta migración; se conservan
> como referencia histórica del módulo previo a `terceros-modelo`. El estado vigente de
> `clientes` (angosta, tabla de ROL) está documentado en
> [`../terceros/base_de_datos.md`](../terceros/base_de_datos.md), sección
> "`clientes` / `proveedores` (rol...)".

Clientes es el módulo dueño de las 4 tablas siguientes.

## `clientes`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. Generada por Postgres al insertar (`repository.py:44-45`). |
| `drogueria_id` | FK a `droguerias`. Fijada al crear con la del solicitante (`service.py:105`); usada como filtro de tenant en `listar_clientes` (`repository.py:36`) y en la comparación de pertenencia de `obtener_cliente` (`service.py:128`, RN-CLIENTES-001). |
| `codigo_interno` | Nullable. No escrita por `crear_cliente` de este módulo (no aparece en el dict de `service.py:102-117`) — ver [`pendientes.md`](./pendientes.md). Sí la usa `imports/repository.py` para matching por lote (fuera de este módulo, ver [`arquitectura.md`](./arquitectura.md)). |
| `nombre` | NOT NULL. Escrita al crear (`service.py:106`), actualizable parcialmente (`service.py:137`). Usada para ordenar el listado (`repository.py:41`). |
| `tipo` | `TipoCliente` (`Literal`, `models.py:10`). Escrita al crear, actualizable parcialmente. |
| `direccion`, `ciudad`, `provincia`, `codigo_postal` | Nullable. Escritas al crear, actualizables parcialmente. |
| `plazo_pago_dias`, `condiciones_pago` | Nullable. Escritas al crear, actualizables parcialmente. |
| `activo` | BOOLEAN. Filtro opcional en `listar_clientes` (`repository.py:39-40`, query param `activo` del router); forzada a `False` por `soft_delete_cliente` (`repository.py:57`). |
| `deleted_at`, `deleted_by` | Escritas únicamente por `soft_delete_cliente` (`repository.py:54-56`). Filtro `is_("deleted_at", None)` en `obtener_cliente` (`repository.py:23`) y `listar_clientes` (`repository.py:37`) — un cliente soft-deleted deja de ser visible por este módulo. |
| `created_by`, `updated_by` | `created_by`/`updated_by` escritas al crear (`service.py:114-115`); `updated_by` reescrita en cada `actualizar_cliente` (`service.py:138`). |

**CRUD**: Create (`repository.py:44-45`), Read (`buscar_cliente` acotado a
`id, drogueria_id` para validación de pertenencia, `repository.py:7-15`;
`obtener_cliente` completo, `repository.py:18-27`; `listar_clientes`,
`repository.py:30-41`), Update (`repository.py:48-49`), soft-Delete
(`repository.py:52-59`).

## `cliente_contactos` (tabla eliminada — reemplazada por `terceros_contactos`)

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `cliente_id` | FK a `clientes`. Escrita al crear (`service.py:154`); usada para filtrar el listado (`repository.py:70`) y para validar pertenencia en `actualizar_contacto` (`service.py:174`, RN-CLIENTES-006). |
| `drogueria_id` | FK a `droguerias`. Escrita al crear (`service.py:155`), no leída por este módulo tras la escritura. |
| `nombre` | NOT NULL. Escrita al crear, actualizable parcialmente. |
| `cargo`, `email`, `telefono`, `notas` | Nullable. Escritas al crear, actualizables parcialmente. |
| `es_principal` | BOOLEAN, default `False` en `ClienteContactoCreate` (`models.py:56`). Usada para ordenar el listado, descendente (`repository.py:71`). |
| `activo` | Existe en `ClienteContactoUpdate`/`ClienteContactoOut` (`models.py:67`, `:79`) y es escribible vía `PATCH`, pero **ningún query de este módulo la usa como filtro** — sin efecto funcional confirmado. Ver [`pendientes.md`](./pendientes.md) P3. |

**CRUD**: Create (`repository.py:62-63`), Read (`listar_contactos`,
`repository.py:66-74`; `buscar_contacto` acotado a validar pertenencia,
`repository.py:81-85`), Update (`repository.py:77-78`). Sin Delete.

**Resuelto en `terceros-modelo`**: `terceros_contactos.activo` sí es filtrable por
defecto (D4) — a diferencia de `cliente_contactos.activo` arriba.

## `cliente_formato_documentos`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `cliente_id` | FK a `clientes`. Parte de la clave `UNIQUE(cliente_id, doc_type)` (RN-CLIENTES-003) usada para decidir si `upsert_formato_documento` actualiza o crea (`service.py:50-66`). |
| `drogueria_id` | FK a `droguerias`. Escrita solo al crear (`service.py:62`), no en el `campos` reutilizado por el update (`service.py:41-48`). |
| `doc_type` | `DocType` (`Literal`, `models.py:6`). Segunda parte de la clave `UNIQUE(cliente_id, doc_type)`. |
| `descripcion_estructura`, `instrucciones_prompt` | Nullable. `instrucciones_prompt` es el campo que **lee directo `services/extraccion/main.py`** (`_resolver_formato_prompt`, líneas 122-149) para enriquecer el prompt de Gemini — ver [`arquitectura.md`](./arquitectura.md). |
| `archivo_ejemplo_path`, `archivo_ejemplo_nombre` | Nullable. |
| `activo` | BOOLEAN, default `True` en `ClienteFormatoDocumentoUpsert` (`models.py:88`). Este módulo la escribe pero no la filtra en ningún query propio; **sí la filtra `services/extraccion/main.py:137`** (`.eq("activo", True)`) — el efecto de este campo vive fuera de este módulo. |
| `actualizado_por` | Escrita en cada upsert con el `usuario_id` del solicitante (`service.py:47`). |

**CRUD**: Create/Update vía upsert real (`upsert_formato_documento`, `service.py:29-66`
→ `repository.py:102-104` o `:106-115`), Read (`buscar_formato_documento` acotado a
`cliente_id`+`doc_type`, `repository.py:88-99`; `listar_formato_documentos`,
`repository.py:118-126`). Sin Delete.

## `cliente_observaciones`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `cliente_id` | FK a `clientes`. Escrita al crear (`service.py:86`), filtro del listado (`repository.py:137`). |
| `drogueria_id` | FK a `droguerias`. Escrita al crear (`service.py:87`). |
| `categoria` | `CategoriaObservacion` (`Literal`, `models.py:7-9`), default `"general"` (`models.py:103`). |
| `observacion` | NOT NULL. |
| `creado_por` | Escrita con el `usuario_id` del solicitante (`service.py:90`). |
| `created_at` | No escrita explícitamente por este módulo (asumido default de la columna); usada para ordenar el listado descendente (`repository.py:138`). |

**CRUD**: Create (`repository.py:129-130`), Read (`listar_observaciones`,
`repository.py:133-141`). Sin Update ni Delete.

## Resumen CRUD y soft-delete

| Tabla | CRUD | Soft-delete |
|---|---|---|
| `clientes` | C/R/U/soft-D | Sí — único caso del módulo. `deleted_at`/`deleted_by`/`activo=False` (`repository.py:52-59`). |
| `cliente_contactos` | C/R/U | No. |
| `cliente_formato_documentos` | C/U (upsert)/R | No. |
| `cliente_observaciones` | C/R | No (sin update ni delete). |

Sobre el resto de las políticas RLS de estas 4 tablas: no se encontró un archivo
equivalente a `docs/schema/rls_final.sql` con las policies de estas tablas citado en
el descubrimiento ni verificado en esta sesión más allá de lo que confirma
D-CLIENTES-002 (RLS de `cliente_formato_documentos` sin `superadmin` en INSERT/UPDATE,
ver [`decisiones.md`](./decisiones.md)) — pendiente de definición funcional si se
necesita el detalle completo de cada policy.
