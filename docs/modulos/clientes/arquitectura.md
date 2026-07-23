# Arquitectura — Clientes

## Dependencias hacia Core

Clientes no importa de ningún otro módulo de negocio de `presupuestacion/` (confirmado
por inspección de imports de los 5 archivos del módulo); depende exclusivamente de
Core.

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 12 endpoints (`router.py:30`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en los 8 endpoints GET y en los 4 POST/PATCH de sub-recursos para la validación previa de pertenencia (`router.py:31`). |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por los 7 wrappers `*_para_endpoint` de `service.py` (`service.py:14`). |
| `NotFoundError`, `ValidationError` | `core/exceptions.py` | Levantadas por `service.py` (`service.py:15`). |
| `ForbiddenError`, `NotFoundError` | `core/exceptions.py` | Levantadas por `router.py` en `_validar_cliente_y_obtener_drogueria_id` (`router.py:32`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.

## Patrón de doble validación de tenant (router + service)

Para los 3 sub-recursos, la pertenencia del cliente a la droguería del solicitante se
valida **dos veces**, de forma independiente, con implementaciones distintas:

1. **En el router**, con `user_client` (con RLS), vía
   `_validar_cliente_y_obtener_drogueria_id` (`router.py:123-139`): hace su propio
   `SELECT id, drogueria_id` sobre `clientes`, y levanta `ForbiddenError` si
   `usuario.rol != "superadmin"` y la droguería no coincide (`router.py:137-138`), o
   `NotFoundError` si el cliente no existe (`router.py:133-134`).
2. **En `service.py`**, con `service_client` (sin RLS), vía
   `_validar_cliente_de_la_drogueria` (`service.py:18-26`): hace su propio
   `repo.buscar_cliente`, y levanta `ValidationError` si la droguería no coincide
   (`service.py:25`), o `NotFoundError` si el cliente no existe (`service.py:23`).

Ambas validaciones son necesarias en la práctica porque las escrituras de sub-recursos
corren con `service_client` (ver D-CLIENTES-008 en [`decisiones.md`](./decisiones.md)):
si solo existiera la validación del router, un wrapper `*_para_endpoint` llamado sin
pasar antes por el router quedaría sin ninguna verificación de tenant, porque
`service_client` bypasea RLS por completo. El resultado es un mismo problema de fondo
(tenant isolation) resuelto dos veces, con dos excepciones distintas
(`ForbiddenError` vs `ValidationError`) — ver [`pendientes.md`](./pendientes.md) P2.

```
POST/PATCH /clientes/{id}/contactos|formato-documentos|observaciones
              │
   Depends(require_roles(*_ROLES_ESCRITURA))
              │
   Depends(get_user_client)  ──►  _validar_cliente_y_obtener_drogueria_id
   (router.py:31)                  (router.py:123-139, user_client, CON RLS)
              │                    → ForbiddenError si droguería no coincide
              │                    → NotFoundError si el cliente no existe
              ▼
   *_para_endpoint (service.py)
              │
   get_service_client() (SIN RLS)
              │
   _validar_cliente_de_la_drogueria
   (service.py:18-26, SEGUNDA validación, independiente)
              │                    → ValidationError si droguería no coincide
              │                    → NotFoundError si el cliente no existe
              ▼
   repository.py (INSERT/UPDATE con service_client)
```

## Acoplamiento a nivel de tabla (fuera de este código Python)

Dos acoplamientos reales no pasan por `clientes/repository.py` ni por `clientes/service.py`:

### Intra-servicio: `services/presupuestacion/imports/`

`services/presupuestacion/imports/repository.py:141-185` implementa su propio bloque
`-- clientes --` con 5 funciones (`mapear_clientes_por_codigo`,
`codigos_activos_clientes`, `insertar_clientes`, `actualizar_cliente`,
`desactivar_clientes`) que hacen CRUD directo sobre la tabla `clientes` para la carga
masiva por `codigo_interno`, en paralelo y sin relación de código con
`clientes/repository.py`. Es el mismo patrón que ya usa `imports/` para `productos` y
`proveedores` (bloques hermanos en el mismo archivo). Este es un hallazgo verificado
en esta sesión que no figuraba en el descubrimiento previo del módulo: la afirmación de
que "ningún otro módulo de `presupuestacion/` importa este módulo" sigue siendo cierta
a nivel de imports de Python, pero no cubre el acoplamiento a nivel de tabla.

### Cross-servicio: `services/extraccion/`

```
clientes/router.py (POST /clientes/{id}/formato-documentos)
      │
      ▼
cliente_formato_documentos (tabla Supabase compartida)
      │
      │  (sin ningún código Python compartido)
      ▼
services/extraccion/main.py:_resolver_formato_prompt (líneas 122-149)
      │  SELECT id, instrucciones_prompt WHERE cliente_id=? AND doc_type=? AND activo=True
      │  (línea 137)
      ▼
Prompt de Gemini enriquecido con instrucciones_prompt del cliente
```

`services/extraccion/routers/clientes.py` (`listar_activos`, líneas 29-54) hace lo
mismo con la tabla `clientes`: `SELECT id, nombre ... WHERE activo=True` (línea 47),
para poblar el selector de cliente del formulario de carga de documentos.

Ambos son acoplamientos de **esquema compartido**, no de código: `services/extraccion/`
no importa nada de `services/presupuestacion/clientes/`, construye sus propias queries
Supabase contra las mismas tablas. Esto significa que este módulo controla
indirectamente, vía `POST /clientes/{id}/formato-documentos`, qué instrucciones recibe
el prompt de extracción de otro backend del monorepo — un cambio en el esquema de
`cliente_formato_documentos` (por ejemplo, renombrar `instrucciones_prompt`) rompería
`services/extraccion/main.py` sin que ningún import de Python lo señalara en tiempo de
desarrollo.
