# Pendientes — Auditoría técnica de Droguerías

Clasificación P1 (ausencia de una capacidad esperada) / P2 (deuda técnica relevante) /
P3 (menor), verificada contra el código y los tests reales en esta sesión.

## P1 — Ausencia de auditoría

1. **Ninguna mutación de este módulo queda registrada en `historial_cambios`.**
   Confirmado por grep exhaustivo en esta sesión: 0 referencias a `core.audit`,
   `registrar_cambio`, `registrar_cambios` o `registrar_evento_ciclo_vida` en los 4
   archivos fuente. [IMPLEMENTADO] el hecho. Es particularmente sensible acá porque
   este módulo administra la tabla raíz del multi-tenant: crear, editar o eliminar una
   droguería no deja rastro de quién lo hizo ni cuándo — ni siquiera hay columnas
   `created_by`/`updated_by` en la tabla (a diferencia de `clientes`). Ver
   `docs/modulos/core/` para el mecanismo de auditoría que otros módulos sí usan.

## P2 — Deuda técnica relevante

1. **`droguerias.activa` no tiene ningún efecto funcional confirmado en este
   repositorio.** Es escribible vía `PATCH` (`models.py:36`) y se expone en
   `DrogueriaOut` (`models.py:57`), pero: `GET /droguerias` no la filtra
   (`router.py:17-24`, sin query param ni condición fija), y
   `core/auth.py:39` — que resuelve `drogueria_id`/`rol` del solicitante en cada
   request — solo lee `usuarios.activo`, nunca `droguerias.activa`. No se encontró
   ningún otro punto del backend (`presupuestacion/` ni `extraccion/`) que lea este
   campo. [IMPLEMENTADO] el hecho de que no hay lectura del campo fuera de la
   respuesta del propio `DrogueriaOut`. Esto significa que "desactivar una empresa" vía
   `PATCH /droguerias/{id}` con `activa=false` no bloquea el login de sus usuarios, no
   la oculta de ningún listado, y no impide ninguna operación — es un campo de solo
   apariencia hoy. Pendiente de definición funcional si se espera que `activa` bloquee
   acceso (equivalente a una suspensión de cuenta) o si es solo informativo.

2. **Dos mecanismos de "dar de baja" sin relación entre sí: `activa=false` y
   `DELETE` (hard).** `activa` sugiere una desactivación reversible; `DELETE` es
   irreversible y solo funciona si no hay datos asociados (RN-DROGUERIAS-004). No hay
   código que los relacione (por ejemplo, forzar `activa=false` antes de permitir un
   `DELETE`, o impedir operaciones de otros módulos cuando `activa=false`). Ver
   D-DROGUERIAS-002 en [`decisiones.md`](./decisiones.md).

3. **RLS (`droguerias_upd`) más permisiva que la política real de la API, sin ningún
   test que lo señale.** Ver D-DROGUERIAS-003 en [`decisiones.md`](./decisiones.md). Si
   un cambio futuro reemplaza `service_client` por `user_client` en el `PATCH` sin
   revisar la policy, un `admin` empezaría a poder editar su propia droguería sin que
   ningún test de este módulo (que solo cubre `service.py` con `service_client`) lo
   detecte.

## P3 — Menor

1. **Dos implementaciones de la misma query de lectura por `id`.**
   `repository.py:obtener_drogueria` (`repository.py:6-8`) y el `SELECT` inline de
   `router.py:obtener_drogueria_endpoint` (`router.py:33`) hacen la misma consulta
   (`SELECT ... WHERE id = ?`), una sin RLS (consumida solo por `service.py` para
   chequeos de existencia) y otra con RLS (expuesta por el `GET` HTTP). Ver
   D-DROGUERIAS-004 en [`decisiones.md`](./decisiones.md).

2. **Sin test de integración HTTP para el 403 de `require_roles("superadmin")`.**
   `tests/droguerias/test_service.py` prueba `service.py` directo con
   `service_client`, sin pasar nunca por `router.py` ni por `require_roles` — el 403
   de RN-DROGUERIAS-005 no tiene cobertura automatizada en este repositorio, solo
   verificación por lectura de código.

3. **Sin validación de unicidad de `cuit` en este módulo.** `crear_drogueria`
   (`service.py:12-13`) no chequea si ya existe una droguería con el mismo `cuit`
   antes de insertar. No se pudo confirmar en esta sesión si existe una constraint
   `UNIQUE` a nivel de columna en la base — pendiente de definición funcional.

4. **Sin paginación en `GET /droguerias`.** `router.py:17-24` devuelve siempre el
   conjunto completo de filas visible por RLS, sin `limit`/`offset` ni cursor.
   [IMPLEMENTADO] el hecho de que no existe paginación; en la práctica el número de
   droguerías (empresas cliente del sistema) es previsiblemente bajo, a diferencia de
   listados como `clientes` o `productos` — impacto probablemente menor, pero no
   verificable sin datos de volumen real.
