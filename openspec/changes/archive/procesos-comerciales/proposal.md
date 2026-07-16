# Proposal: Creación y listado de procesos comerciales

**Estado: archivado/completado.** Documentado retroactivamente el 2026-07-15 para adoptar la
convención de `openspec/` (ver `openspec/AGENTS.md`) — el código ya estaba implementado y
verificado antes de escribir este proposal.

## Intent

El modal "+ Nueva Licitación/Cotización" del frontend (dentro de la pantalla de carga de
documentos) existía en la UI pero no podía crear nada: no había ningún endpoint en
`services/presupuestacion` para crear ni listar `procesos_comerciales`. El diagnóstico (sesión
2026-07-14) confirmó con evidencia real (logs de uvicorn + `list_tables` en vivo) que era un gap
de backend, no un bug de frontend.

Se necesitaba: `POST /procesos-comerciales` para crear, `GET /procesos-comerciales` para poblar el
selector de "licitación vinculada" en el form de carga, y recablear el modal del frontend contra
esos endpoints con JWT real (sin bypass de auth — ya disponible desde el change
[`archive/login-frontend`](../login-frontend/)).

## Scope

### Incluido
- `POST /procesos-comerciales` en `services/presupuestacion` (nuevo módulo
  `procesos_comerciales/`: models, repository, service, router).
- `GET /procesos-comerciales` (listado, filtrable por `activos`).
- Resolución de `drogueria_id` desde el perfil del usuario autenticado (no viene del body).
- Auditoría de creación vía `registrar_evento_ciclo_vida` (patrón ya establecido en
  `eventos/service.py`).
- `require_roles` en ambos endpoints (lectura: roles amplios incluyendo `compras`; escritura:
  roles comerciales/gerenciales, sin `superadmin` ni `compras`).
- Validación de reglas de negocio: una cotización no admite campos de seguimiento de licitación
  (`apertura`, `vencimiento`, `modalidad`, `tipo_gestion`, `comparativa_pedida`) — constraint real
  de la tabla (`ck_proc_cotizacion_sin_seguimiento`, no versionada como migración en el repo,
  confirmada empíricamente contra la BD de test).
- Recableo de `NuevaLiciCotiDialog.tsx` y `FormCard.tsx` (dentro de
  `frontend/src/features/carga-documentos/`) contra los endpoints reales.

### Explícitamente fuera de scope
- Edición o eliminación de procesos comerciales (no hay `PATCH`/`DELETE`).
- Transiciones de estado (`abierto` → `presupuestado` → ...) — el proceso se crea siempre en su
  estado inicial; el resto del ciclo de vida pertenece a pantallas futuras (matching,
  presupuestos).
- Vincular el listado de "cargas recientes" de la pantalla de carga de documentos contra
  `procesos_comerciales` — ese gap (`GET /api/documentos` en `services/extraccion` sigue
  apuntando a la tabla vieja `licitaciones`) queda para el change
  [`carga-documentos`](../../carga-documentos/).

## Approach

Mismo patrón arquitectónico que el resto de `services/presupuestacion`: capa por dominio
(`models.py`/`repository.py`/`service.py`/`router.py`), `require_roles` como dependency de FastAPI,
`get_service_client()` para escrituras que necesitan bypassear RLS de forma controlada (la
creación resuelve `drogueria_id` del usuario, no confía en el body), auditoría centralizada vía
`registrar_evento_ciclo_vida`.

## Riesgos

Ninguno relevante — sigue un patrón ya validado en el resto del backend
(`catalogo/router.py` como referencia de `require_roles`, `eventos/service.py` como referencia de
auditoría).
