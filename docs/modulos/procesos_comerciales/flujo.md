# Flujos — Procesos Comerciales

Los 3 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en esta
sesión.

## Flujo 1 — Alta de licitación (`POST /procesos-comerciales`, `clase="licitacion"`)

1. El router exige `require_roles(*_ROLES_ESCRITURA)` — `("admin", "gerencia",
   "lider_comercial", "comercial")` (`router.py:18`, `:36`).
2. `crear_proceso_comercial_endpoint` llama a
   `crear_proceso_comercial_para_endpoint(drogueria_id=usuario.drogueria_id,
   body=body, usuario_id=usuario.id)` (`router.py:38-40`).
3. `crear_proceso_comercial_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_proceso_comercial` (`service.py:72-77`).
4. `crear_proceso_comercial` llama a `_validar_campos_de_seguimiento(body)`
   (`service.py:40`); como `body.clase != "cotizacion"`, la función retorna de
   inmediato sin validar nada (`service.py:17-18`).
5. `repo.crear_proceso_comercial` hace el INSERT con `drogueria_id`, `cliente_id`,
   `clase`, `nombre`, `categoria_id`, `monto_estimado`, `notas`, `apertura`,
   `vencimiento`, `tipo_gestion`, `modalidad`, `comparativa_pedida`, `created_by` y
   `updated_by` (`service.py:41-59`, `repository.py:12-13`) — sin `estado`
   (RN-PROCESOS-004).
6. `registrar_evento_ciclo_vida` audita la creación (`service.py:60-68`,
   RN-PROCESOS-003).
7. El endpoint responde con `ProcesoComercialOut` (`router.py:33`,
   `response_model=ProcesoComercialOut`).

## Flujo 2 — Alta de cotización (`POST /procesos-comerciales`, `clase="cotizacion"`)

Idéntico al Flujo 1, salvo el paso 4:

4. `_validar_campos_de_seguimiento(body)` **sí** ejecuta la guarda RN-PROCESOS-001
   (`service.py:19-34`): arma la lista de campos de seguimiento seteados
   (`apertura`, `vencimiento`, `modalidad`, `tipo_gestion`, `comparativa_pedida`,
   `service.py:19-29`) y, si hay al menos uno, corta con `ValidationError` **antes**
   de llegar al paso 5 — el INSERT nunca se ejecuta (`service.py:30-34`).

Si la cotización no trae ningún campo de seguimiento, el flujo continúa igual que el
Flujo 1 desde el paso 5.

## Flujo 3 — Listado y filtrado (`GET /procesos-comerciales?activos=true|false`)

1. El router exige `require_roles(*_ROLES_LECTURA)` — `("superadmin", "admin",
   "gerencia", "lider_comercial", "comercial", "compras")`, más amplio que
   `_ROLES_ESCRITURA` (`router.py:19`, `:25`).
2. `listar_procesos_comerciales_endpoint` usa `user_client` inyectado con
   `Depends(get_user_client)` (`router.py:26`) — a diferencia de la creación (Flujos 1
   y 2), que usa `service_client`.
3. Llama a `listar_procesos_comerciales(user_client, drogueria_id=usuario.drogueria_id,
   activos=activos)` (`router.py:28-30`), con `activos` tomado del query param
   (default `True`, `router.py:24`).
4. `service.listar_procesos_comerciales` es un passthrough directo a
   `repo.listar_procesos_comerciales` (`service.py:80-83`), sin lógica adicional.
5. `repo.listar_procesos_comerciales` filtra por `drogueria_id` y `deleted_at IS NULL`
   siempre (`repository.py:20-23`); si `activos=True`, aplica además
   `not_.in_("estado", _ESTADOS_TERMINALES)` (RN-PROCESOS-002, `repository.py:25-26`);
   ordena por `nombre` (`repository.py:27`).
6. El endpoint responde con `list[ProcesoComercialResumen]` (`router.py:22`,
   `response_model`) — payload mínimo: `id, nombre, clase, estado`
   (`repository.py:21`, `models.py:35-39`).
