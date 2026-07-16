# Tasks: Creación y listado de procesos comerciales

**Change:** procesos-comerciales
**Estado:** completado y archivado
**Commits:**
- `a3925a8` — feat: agregar POST /procesos-comerciales en presupuestacion (2026-07-15 09:35)
- `917e136` — feat: agregar GET /procesos-comerciales y recablear el dialogo del frontend (2026-07-15 10:20)

---

## Backend — módulo nuevo

- [x] `procesos_comerciales/models.py` — `ProcesoComercialCreate`, `ProcesoComercialResumen`, `ProcesoComercialOut`
- [x] `procesos_comerciales/repository.py`
- [x] `procesos_comerciales/service.py` — `crear_proceso_comercial`, `_validar_campos_de_seguimiento`, `listar_procesos_comerciales`
- [x] `procesos_comerciales/router.py` — `POST` y `GET /procesos-comerciales`
- [x] `drogueria_id` resuelto del usuario autenticado, no del body
- [x] Validación de constraint `ck_proc_cotizacion_sin_seguimiento` en `service.py` (evita 500 crudo de Postgres, devuelve 422 claro)
- [x] Auditoría vía `registrar_evento_ciclo_vida` en la creación
- [x] `require_roles` en ambos endpoints (lectura y escritura con sets de roles distintos)
- [x] `GET` filtra `activos` excluyendo estados terminales (mismo criterio que el legacy `listar_activas`)

## Frontend — recableo

- [x] `frontend/src/lib/api/procesosComerciales.ts` — `crearProcesoComercial`, `listarProcesosComerciales`
- [x] `NuevaLicitacionDialog.tsx` renombrado a `NuevaLiciCotiDialog.tsx` (el nombre viejo quedó desactualizado — crea cualquiera de las dos clases vía toggle)
- [x] Toggle oculta `apertura`/`modalidad` cuando `clase === "cotizacion"` (el backend los rechaza con 422)
- [x] `FormCard.tsx` lista `procesos_comerciales` en vez del endpoint legacy roto de `licitaciones`
- [x] Invalidación de query `["procesos-comerciales"]` al crear, para refrescar el selector sin reload

## Archivado

- [x] Change movido a `openspec/changes/archive/procesos-comerciales/` (retroactivo, 2026-07-15)

## Fuera de este change (ver PROGRESS.md)

- [ ] `GET /api/documentos` en `services/extraccion` sigue roto (tabla `licitaciones` inexistente) —
      pertenece al change `carga-documentos`, no a este.
