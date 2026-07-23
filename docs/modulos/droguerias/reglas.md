# Reglas — Droguerías

Todas las reglas fueron verificadas contra el código real (`service.py`, `router.py`,
`models.py`) y sus tests (`tests/droguerias/test_service.py`) en esta sesión.

### RN-DROGUERIAS-001 — El CUIT/CUIL debe tener formato `NN-NNNNNNNN-N`, sin validar dígito verificador

- **Descripción**: `_validar_formato_cuit` valida con una regexp que el CUIT tenga
  exactamente 2 dígitos, guion, 8 dígitos, guion, 1 dígito. **No** calcula ni valida el
  dígito verificador real de un CUIT/CUIL argentino (checksum) — solo la forma.
- **Condición**: `_CUIT_RE.match(valor)` con `_CUIT_RE = re.compile(r"^\d{2}-\d{8}-\d$")`.
- **Resultado**: `ValueError("El CUIT/CUIL debe tener el formato NN-NNNNNNNN-N")` si no
  matchea, propagado por Pydantic como `ValidationError` (422 en la API).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/droguerias/models.py:5-11`, aplicada en
  `DrogueriaCreate` (`models.py:24`, obligatoria) y en `DrogueriaUpdate`
  (`models.py:39-44`, solo si el campo se envía — `if valor is None: return valor`).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/droguerias/test_service.py:82-84`
  (`test_crear_drogueria_rechaza_cuit_con_formato_invalido`, prueba `"20999999991"` sin
  guiones) y `tests/droguerias/test_service.py:87-89`
  (`test_actualizar_drogueria_rechaza_cuit_con_formato_invalido`, prueba
  `"no-es-un-cuit"`). Un CUIT con formato correcto pero dígito verificador inválido
  (por ejemplo `20-00000000-0`) pasaría esta validación sin error — no hay ningún
  checksum real en el código.

### RN-DROGUERIAS-002 — Actualizar o eliminar una droguería inexistente lanza `NotFoundError`

- **Descripción**: tanto `actualizar_drogueria` como `eliminar_drogueria` (en
  `service.py`) buscan la fila primero con `repo.obtener_drogueria` antes de mutar
  nada.
- **Condición**: `existente is None`.
- **Resultado**: `NotFoundError("No se encontró la droguería")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/droguerias/service.py:19-21` (update),
  `:28-30` (delete).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/droguerias/test_service.py:72-79`
  (`test_actualizar_drogueria_inexistente_lanza_not_found`) y
  `tests/droguerias/test_service.py:102-105`
  (`test_eliminar_drogueria_inexistente_lanza_not_found`).

### RN-DROGUERIAS-003 — `actualizar_drogueria` es una actualización parcial

- **Descripción**: solo se pisan los campos enviados explícitamente en el body; los
  campos no incluidos en el `PATCH` no se tocan.
- **Condición**: cualquier llamada a `actualizar_drogueria`.
- **Resultado**: `body.model_dump(exclude_unset=True)` — `service.py:23`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/droguerias/service.py:23`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/droguerias/test_service.py:41-51`
  (`test_actualizar_drogueria_solo_toca_campos_provistos`, envía solo `activa=False` y
  confirma que `nombre` no cambia) y
  `tests/droguerias/test_service.py:54-69`
  (`test_actualizar_drogueria_asigna_plan`, envía solo `plan_id`).

### RN-DROGUERIAS-004 — Eliminar una droguería con datos asociados lanza `ConflictError`, no falla con un error genérico

- **Descripción**: `eliminar_drogueria` hace un `DELETE` real (no soft-delete). Si la
  fila tiene dependientes por FK (usuarios, clientes, procesos comerciales, etc.),
  Postgres rechaza el `DELETE` con una violación de foreign key; el service atrapa esa
  excepción puntual y la traduce a un error de dominio con mensaje claro.
- **Condición**: `repo.eliminar_drogueria(...)` levanta `postgrest.exceptions.APIError`.
- **Resultado**: `ConflictError("No se puede eliminar: la empresa tiene datos "
  "asociados (usuarios, clientes, procesos comerciales, etc.).")` — mapeado a HTTP 409
  por `core/exceptions.py`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/droguerias/service.py:32-38`.
- **Observaciones**: [IMPLEMENTADO]. Verificada **empíricamente contra una base real**
  en `tests/droguerias/test_service.py:108-126`
  (`test_eliminar_drogueria_con_usuarios_lanza_conflict`, crea una droguería, le crea un
  usuario real con `service_client.auth.admin.create_user` + INSERT en `usuarios`, e
  intenta eliminar la droguería) — no es un test con mocks, ejercita la violación de FK
  real de Postgres.

### RN-DROGUERIAS-005 — Solo `superadmin` puede crear, editar o eliminar una droguería

- **Descripción**: los 3 endpoints de escritura exigen el rol `superadmin`
  explícitamente, sin alternativas — a diferencia de Clientes o Usuarios, no hay un
  segundo rol habilitado para escritura en este módulo.
- **Condición**: `Depends(require_roles("superadmin"))`.
- **Resultado**: `ForbiddenError` (403, mapeado por `core/auth.py`, ver
  [`../core/`](../core/)) si el rol del solicitante no es `superadmin`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/droguerias/router.py:41`, `:50`, `:58`.
- **Observaciones**: [IMPLEMENTADO] a nivel de código (revisión de `router.py`); no se
  encontró un test de integración HTTP en `tests/droguerias/` que ejercite el 403 —
  `tests/droguerias/test_service.py` prueba `service.py` directo, sin pasar por
  `require_roles`. Ver [`pendientes.md`](./pendientes.md) P3.

### RN-DROGUERIAS-006 — La lectura no exige ningún rol específico; el aislamiento lo hace RLS

- **Descripción**: `GET /droguerias` y `GET /droguerias/{id}` solo exigen estar
  autenticado (`Depends(get_current_user)`, sin `require_roles`); qué filas ve cada
  usuario lo decide la policy `droguerias_sel` de Postgres, no una condición en Python.
- **Condición**: `es_superadmin() OR id = get_drogueria_id()` (`docs/schema/rls_final.sql:101`).
- **Resultado**: un `superadmin` ve todas las droguerías; cualquier otro rol solo ve la
  propia droguería (o `NotFoundError` explícito en `router.py:34-35` si pide por `id`
  una que no le pertenece, porque el `SELECT` con RLS simplemente no devuelve la fila).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/droguerias/router.py:17-24`, `:27-36`;
  `docs/schema/rls_final.sql:101`.
- **Observaciones**: [IMPLEMENTADO] a nivel de código y policy SQL. No hay test en este
  repositorio que ejercite la policy RLS end-to-end (los tests de
  `tests/droguerias/test_service.py` usan `service_client`, que bypasea RLS por
  completo) — pendiente de definición si se necesita cobertura de integración HTTP
  contra RLS real.
