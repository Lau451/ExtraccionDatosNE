# Specification: Creación y listado de procesos comerciales

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `services/presupuestacion/procesos_comerciales/models.py` | `ProcesoComercialCreate`, `ProcesoComercialResumen`, `ProcesoComercialOut`. `Clase = "cotizacion" \| "licitacion"`. `Estado` con 8 valores (`abierto` → ... → `cerrado`/`cancelado`). |
| `services/presupuestacion/procesos_comerciales/repository.py` | Acceso a datos (Supabase client). |
| `services/presupuestacion/procesos_comerciales/service.py` | `crear_proceso_comercial`, `crear_proceso_comercial_para_endpoint`, `listar_procesos_comerciales`, `_validar_campos_de_seguimiento`. |
| `services/presupuestacion/procesos_comerciales/router.py` | `POST /procesos-comerciales`, `GET /procesos-comerciales`. |
| `frontend/src/lib/api/procesosComerciales.ts` | `crearProcesoComercial`, `listarProcesosComerciales`. |
| `frontend/src/features/carga-documentos/components/NuevaLiciCotiDialog.tsx` | Modal de creación, wireado contra `crearProcesoComercial`. |
| `frontend/src/features/carga-documentos/components/FormCard.tsx` | Selector "Licitación vinculada", wireado contra `listarProcesosComerciales`. |

## API

### `POST /procesos-comerciales`

- Roles permitidos: `admin`, `gerencia`, `lider_comercial`, `comercial`.
- `drogueria_id` se resuelve del perfil del usuario autenticado (`usuario.drogueria_id`), NUNCA
  del body — evita que un cliente malicioso cree procesos en otra droguería.
- Body: `ProcesoComercialCreate` (`nombre`, `clase`, `cliente_id?`, `categoria_id?`,
  `monto_estimado?`, `notas?`, `apertura?`, `vencimiento?`, `tipo_gestion?`, `modalidad?`,
  `comparativa_pedida`).
- MUST rechazar (`ValidationError`) si `clase == "cotizacion"` y viene seteado cualquiera de:
  `apertura`, `vencimiento`, `modalidad`, `tipo_gestion`, `comparativa_pedida` (truthy).
- MUST registrar un evento de ciclo de vida (`registrar_evento_ciclo_vida`, `tipo_cambio="creacion"`,
  `origen="usuario"`) en la misma operación de creación.
- Devuelve `ProcesoComercialOut` (incluye `id`, `estado` inicial, timestamps).

### `GET /procesos-comerciales`

- Roles permitidos: `superadmin`, `admin`, `gerencia`, `lider_comercial`, `comercial`, `compras`.
- Query param `activos: bool = True` — cuando es `True`, excluye estados terminales
  (`adjudicado`, `perdido`, `cerrado`, `cancelado`). Mismo criterio que el legacy
  `listar_activas` de `licitaciones.py`, adaptado al vocabulario nuevo.
- Filtra por `drogueria_id` del usuario autenticado vía RLS (`get_user_client`, no
  `get_service_client` como en el POST) — no se puede listar de otra droguería.
- Devuelve `list[ProcesoComercialResumen]` (`id`, `nombre`, `clase`, `estado`).

## Scenarios

### Scenario: crear una cotización simple
```
Given: un usuario con rol "comercial" autenticado
When: POST /procesos-comerciales con {nombre, clase: "cotizacion"}
Then: se crea el proceso con drogueria_id del usuario
  AND se registra un evento de ciclo de vida "creacion"
  AND la respuesta incluye estado inicial
```

### Scenario: cotización con campos de seguimiento — rechazada
```
Given: un usuario autenticado
When: POST /procesos-comerciales con {nombre, clase: "cotizacion", apertura: "2026-08-01"}
Then: 4xx ValidationError
  AND el mensaje lista los campos rechazados ("apertura")
  AND no se crea ningún registro
```

### Scenario: crear una licitación con seguimiento
```
Given: un usuario autenticado
When: POST /procesos-comerciales con {nombre, clase: "licitacion", apertura, modalidad: "mail"}
Then: se crea el proceso sin rechazo (los campos de seguimiento son válidos para licitación)
```

### Scenario: listar procesos de otra droguería — no visibles
```
Given: procesos comerciales existentes en droguería A y droguería B
  AND un usuario autenticado pertenece a droguería A
When: GET /procesos-comerciales
Then: solo se devuelven los procesos de droguería A
```

### Scenario: rol sin permiso de escritura
```
Given: un usuario con rol "compras" (solo en _ROLES_LECTURA, no en _ROLES_ESCRITURA)
When: POST /procesos-comerciales
Then: 403 (require_roles rechaza)
```

### Scenario: modal de frontend crea y refresca el selector
```
Given: el usuario abre "+ Nueva" en el form de carga de documentos
  AND completa nombre y clase, y confirma
When: la mutación crearProcesoComercial resuelve OK
Then: se invalida la query ["procesos-comerciales"]
  AND el selector "Licitación vinculada" incluye el nuevo proceso
  AND el dialog se cierra y limpia su estado
```

## Verificación

Implementado y commiteado el 2026-07-15 (`a3925a8`, `917e136`). A diferencia de
[`archive/login-frontend`](../login-frontend/spec.md), no hay confirmación explícita en memoria de
una verificación end-to-end en navegador real para este change puntual — los commits documentan la
implementación y el fix de un bug real detectado (el 500 crudo de Postgres en la validación de
cotización, corregido a 422 con mensaje claro), lo que sugiere que sí hubo prueba manual durante el
desarrollo, pero no está registrado con el mismo nivel de detalle que el login. Si hace falta
certeza total, re-verificar manualmente antes de dar la pantalla "Procesos comerciales" por
cerrada en un sentido más amplio que "el endpoint funciona".
