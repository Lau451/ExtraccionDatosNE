# Ajuste: sacar entregas de la validación de OC + auto-navegación post-carga

## Objetivo

Ajustar el flujo ya shippeado de Tramo 2 (validación de orden de compra) según decisión
del usuario (2026-09-20/21, conversación de rediseño post-merge): la división en entregas
deja de pasar en este paso — se mueve a una fase futura (matching contra presupuesto +
asignación de producto, todavía sin diseñar/bloqueada por Sistemas). Este ajuste NO incluye
esa fase futura, solo saca lo que ya no corresponde de acá y agrega la navegación
automática que el usuario pidió.

## Alcance

### 1. Backend — `_materializar_orden_compra` ya no crea entregas

`services/presupuestacion/extraccion/service.py`:

- Sacar del bloque `try` de `_materializar_orden_compra` todo lo relacionado a entregas:
  `fecha_base`, `modo_manual`, `reparto_automatico`, el `for indice_entrega, entrega in
  enumerate(override.entregas)` completo (incluye `crear_entrega_oc`,
  `insertar_entregas_oc_items`). Confirmar solo crea `ordenes_compra` (sin
  `cantidad_entregas` explícito — la columna tiene `DEFAULT 1`, no hace falta setearla) +
  `oc_items` + el registro de auditoría (`registrar_evento_ciclo_vida`/`registrar_cambio`,
  eso se mantiene igual).
- `entregas_creadas` en el `return` pasa a ser siempre `0` (o sacar el valor del tuple si
  se prefiere una firma más limpia — decisión del implementador, documentar cuál se elige).
- `_validar_orden_compra_override`: sacar la validación de que la suma de `entregas` por
  línea coincide con `cantidad` del renglón (esa validación ya no aplica, `entregas` no
  viaja en el payload).
- `services/presupuestacion/extraccion/models.py`: sacar el campo `entregas: list[EntregaPlanIn]`
  de `OrdenCompraOverride`. **No borrar** la clase `EntregaPlanIn` ni la función
  `repartir_cantidad` (D8) — son utilidades puras, ya testeadas, que la fase futura de
  entregas va a reusar tal cual. Sacar solo lo que conecta esto al flujo de confirmación
  actual.
- `ResultadoValidarExtraccion.entregas_creadas: int = 0` — se puede dejar el campo (con
  default 0, ya que nada lo va a poblar desde acá) en vez de sacarlo, para no romper
  contrato de API sin necesidad — a criterio del implementador.

### 2. Frontend — sacar `EntregasEditor` de la pantalla de validación

`frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.tsx`:

- Sacar el render de `<EntregasEditor>` de la rama `orden_compra`.
- `puedeConfirmar` pierde la condición de "≥1 entrega válida" — queda: cliente confirmado +
  cabecera sin bloqueos (`numero_oc` sin conflicto entre miembros del grupo).
- `construirOrdenCompraOverride()` deja de armar/mandar `entregas` en el payload.
- **No borrar** `EntregasEditor.tsx` ni sus tests — el componente lo va a reusar la fase
  futura de matching+entregas. Solo se deja de invocar desde acá.

### 3. Frontend — auto-navegación tras la carga (solo `orden_compra`)

`frontend/src/features/carga-documentos/components/FormCard.tsx` (o donde corresponda
según el código real — verificar):

- Cuando `tipo === 'ordenes'` y **todos** los `procesarDocumento` del lote (1 o N archivos
  con el mismo `grupoId`) terminan con éxito, navegar automáticamente a
  `/validar-extraccion/{extractionId}` (la primera extracción del lote si son varias — son
  el mismo grupo, cualquiera de las N sirve como entrada). Si alguno de los N falla, no
  navegar — dejar al usuario en la pantalla de carga viendo el error por archivo (mismo
  comportamiento actual de reporte por archivo, no tocar eso).
- Licitación/comparativa **no cambian** — siguen sin auto-navegar, se quedan en "Carga de
  documentos" como hoy. Este comportamiento es específico de `orden_compra`.

## Verificación

- Backend: `pytest tests/extraccion -q -m "not integration"` (0 regresiones respecto al
  baseline post-bugfix, 118 passed) y `pytest tests/extraccion -m integration -q` contra el
  proyecto de test (`grnamollopxdlstcpxhc`) — confirmar en vivo que confirmar una OC ya NO
  crea filas en `entregas_oc`/`entregas_oc_items`.
- Frontend: `cd frontend && corepack pnpm test` (0 regresiones respecto al baseline actual)
  y `corepack pnpm build` limpio.

## Contexto de tooling

- Strict TDD Mode activo. Test runner backend: `pytest tests/` (venv). Test runner
  frontend: `cd frontend && corepack pnpm test`/`build` (no hay workspace root de pnpm,
  `pnpm --filter frontend` falla).
- Proyecto de test Supabase: `grnamollopxdlstcpxhc`.
- No agregar línea de atribución de IA a ningún commit.
- Commit directo en `dev`, sin branch/PR nuevo (mismo patrón que el bugfix anterior de esta
  sesión) — no pushear, el orquestador revisa y pushea.

## Tareas

- [x] 1 [RED] Test backend que confirma que `_materializar_orden_compra` ya NO crea filas en
  `entregas_oc`/`entregas_oc_items` (extender o invertir el test de integración existente
  que sí las esperaba).
  - Unit (rápido, sin DB): `test_materializar_orden_compra_ya_no_crea_entregas` agregado en
    `tests/extraccion/test_orden_compra.py`. Corrido contra el código pre-cambio:
    `pytest tests/extraccion/test_orden_compra.py::test_materializar_orden_compra_ya_no_crea_entregas -q -m "not integration"`
    -> `1 failed` (pydantic `ValidationError: entregas Field required` -- el modelo todavía
    exigía `entregas`).
  - Integración (invertido): `test_validar_orden_compra_materializa_oc_items_y_entregas`
    renombrado a `test_validar_orden_compra_materializa_oc_items_sin_crear_entregas` en
    `tests/extraccion/test_service.py`, assertions invertidas (`entregas_creadas == 0`,
    `entregas_oc`/`entregas_oc_items` vacías). No se pudo correr en RED contra el código
    viejo: el proyecto Supabase de test (`grnamollopxdlstcpxhc`) estaba caído (Cloudflare
    521 "Web server is down") en el momento de escribir el test -- confirmado con el test
    YA EXISTENTE (sin tocar) antes de cualquier cambio de código, no es un problema
    introducido por este trabajo. Se corrió en GREEN más abajo (task 7), cuando el proyecto
    volvió a estar disponible.
- [x] 2 [GREEN] Aplicar los cambios de la sección 1 (backend).
  - `services/presupuestacion/extraccion/models.py`: sacado `entregas: list[EntregaPlanIn]`
    de `OrdenCompraOverride`. `EntregaPlanIn` y `ResultadoValidarExtraccion.entregas_creadas`
    (default 0) se conservan, con comentario explicando por qué.
  - `services/presupuestacion/extraccion/service.py`: `_validar_orden_compra_override` sin
    la validación de suma de entregas por renglón. `_materializar_orden_compra` sin el
    bloque de `crear_entrega_oc`/`insertar_entregas_oc_items` (fecha_base/modo_manual/
    reparto_automático/loop de entregas); `cantidad_entregas` ya no se setea explícito
    (columna con `DEFAULT 1`, confirmado en `docs/schema/extractor_final.sql:1030`);
    `entregas_creadas` del return pasa a ser literal `0`. `repartir_cantidad` (D8) NO se
    tocó -- sigue definida y con sus tests unitarios propios.
  - Evidencia: `pytest tests/extraccion/test_orden_compra.py::test_materializar_orden_compra_ya_no_crea_entregas -q -m "not integration"`
    -> `1 passed`.
- [x] 3 [RED] Test frontend que confirma que `orden_compra` en `ValidarExtraccionDetalle` NO
  renderiza `EntregasEditor`, y que `puedeConfirmar` no depende de entregas.
  - `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.test.tsx`: sacado el
    `vi.mock('./components/EntregasEditor', ...)`; test de render reescrito para afirmar
    ausencia del label real "Cantidad de entregas"; test de `puedeConfirmar` reescrito sin
    la condición de entregas; test "con entregas bloqueadas" eliminado (esa rama ya no
    existe); test de payload reescrito para afirmar `not.toHaveProperty('entregas')`.
  - Evidencia RED: `corepack pnpm test -- --run src/features/validar-extraccion/ValidarExtraccionDetalle.test.tsx`
    -> `2 failed | 26 passed (27)` (test de render y test de payload, ambos por el
    `EntregasEditor` real todavía montado/enviando `entregas`).
- [x] 4 [GREEN] Aplicar los cambios de la sección 2 (frontend).
  - `ValidarExtraccionDetalle.tsx`: sacado el import y el render de `<EntregasEditor>`, el
    estado `entregas`/`entregasBloqueadas`, la clave `entregas` de
    `construirOrdenCompraOverride()`, y la condición de entregas en `puedeConfirmar`.
    `EntregasEditor.tsx` y su test propio NO se tocaron.
  - `frontend/src/lib/api/extracciones.ts`: sacado el campo `entregas: EntregaPlanIn[]` de
    la interfaz `OrdenCompraOverride` (necesario para que `pnpm build`/tsc no rompiera --
    ver "Deviations" abajo). La interfaz `EntregaPlanIn` se conserva sin uso (mismo criterio
    que el backend).
  - Evidencia: `corepack pnpm test -- --run src/features/validar-extraccion/ValidarExtraccionDetalle.test.tsx`
    -> `195 passed (195)` (todo el archivo de tests del proyecto, no solo este spec).
- [x] 5 [RED] Test frontend de `FormCard` (o donde corresponda) que confirma la
  auto-navegación tras `tipo='ordenes'` exitoso (1 archivo y caso agrupado N archivos), y
  que licitación/comparativa NO navegan.
  - Confirmado el archivo real: `frontend/src/features/carga-documentos/components/FormCard.tsx`.
  - 4 tests agregados en `FormCard.test.tsx` (describe nuevo "auto-navegación post-carga"):
    1 archivo OK navega con `extractionId`/`rowCount` reales; N=3 agrupados TODOS OK navega
    UNA vez; 1 de N falla NO navega; tipo='licitaciones' OK NO navega. Mock de
    `@tanstack/react-router` (`useNavigate`) agregado al archivo (no existía).
  - Evidencia RED: `corepack pnpm test -- --run src/features/carga-documentos/components/FormCard.test.tsx`
    -> `2 failed | 197 passed (199)` (los 2 tests que esperaban `navigate` llamado; los de
    "falla"/"licitaciones" ya pasaban porque hoy nunca se navega).
- [x] 6 [GREEN] Aplicar los cambios de la sección 3 (frontend).
  - `FormCard.tsx`: `esperarNuevoDocumento` ahora devuelve la lista de `DocumentoReciente`
    (antes no devolvía nada). `mutationFn` devuelve `{resultados, documentos}`. `onSuccess`:
    si `tipo === 'ordenes'` y TODOS los `resultados` tienen `ok`, navega a
    `/validar-extraccion/$extractionId` con el primer documento nuevo devuelto (mismo grupo,
    cualquiera de los N sirve). Licitación/comparativa sin cambios (nunca navegan). JSX de
    la lista de resultados por archivo actualizado a `mutation.data?.resultados`.
  - Evidencia: `corepack pnpm test -- --run src/features/carga-documentos/components/FormCard.test.tsx`
    -> `199 passed (199)`.
- [x] 7 [REFACTOR] Correr la verificación completa (arriba) y confirmar 0 regresiones fuera
  de este alcance.
  - `pytest tests/extraccion -q -m "not integration"`: baseline (antes de tocar código)
    `118 passed, 39 deselected`; final `115 passed, 39 deselected` (118 - 4 tests de
    validación de entregas eliminados por lógica removida + 1 test nuevo = 115; sin
    regresiones).
  - `pytest tests/extraccion -m integration -q` contra `grnamollopxdlstcpxhc` (proyecto
    volvió a estar disponible): `39 passed, 115 deselected` -- incluye
    `test_validar_orden_compra_materializa_oc_items_sin_crear_entregas`, confirmado EN VIVO
    que confirmar una OC ya no crea filas en `entregas_oc`/`entregas_oc_items`.
  - `pytest tests/ -q -m "not integration"` (repo completo): baseline `383 passed, 449
    deselected`; final `380 passed, 449 deselected` (mismo delta -3 de arriba, 0
    regresiones fuera de `tests/extraccion`).
  - `cd frontend && corepack pnpm test -- --run`: baseline `196 passed (27 test files)`;
    final `199 passed (27 test files)` (+4 tests nuevos de FormCard, -1 test eliminado de
    ValidarExtraccionDetalle; sin regresiones).
  - `cd frontend && corepack pnpm build`: limpio (`tsc -b && vite build`, sin errores).
    `frontend/src/routeTree.gen.ts` se reordenó como efecto secundario del build (problema
    recurrente conocido de este repo) -- revertido con
    `git checkout -- frontend/src/routeTree.gen.ts` antes de dejar el árbol de trabajo.

### Deviations (desvíos respecto al diseño original de esta tarea)

1. **`frontend/src/lib/api/extracciones.ts` (no listado explícitamente en el alcance de la
   sección 2, pero necesario):** se sacó el campo `entregas: EntregaPlanIn[]` de la interfaz
   TS `OrdenCompraOverride`. La sección 2 del alcance solo mencionaba
   `ValidarExtraccionDetalle.tsx`, pero como esa interfaz es un "espejo literal" tipado del
   modelo Pydantic y `construirOrdenCompraOverride()` se pasa por `mutation.mutate({
   orden_compra: ... })` (tipado contra `ValidarExtraccionPayload.orden_compra?:
   OrdenCompraOverride`), dejar `entregas` como campo requerido en la interfaz hacía fallar
   `tsc -b` (propiedad faltante). Cambio mínimo y symétrico con el lado backend: se sacó el
   campo, se conservó la interfaz `EntregaPlanIn` sin uso (mismo criterio que
   `EntregaPlanIn`/`repartir_cantidad` del lado backend).
2. **Supabase test project caído durante parte del trabajo:** al momento de escribir el test
   invertido de task 1, `grnamollopxdlstcpxhc` respondía Cloudflare 521 ("Web server is
   down") -- confirmado corriendo el test de integración YA EXISTENTE (sin ningún cambio de
   código de esta tarea) contra el proyecto, antes de tocar nada. No fue posible confirmar el
   estado RED de ese test específico contra el código viejo en vivo por este motivo (se
   documentó el RED "lógico": el código viejo SÍ crea entregas, por diseño). El proyecto
   volvió a estar disponible más tarde en la misma sesión y el test corrió en GREEN sin
   problemas (ver task 7).
3. **Tests de `_validar_orden_compra_override` para la validación de suma de entregas
   eliminados, no solo editados:** `test_entregas_vacia_viola_min_length_del_modelo`,
   `test_entregas_no_vacia_sin_desglose_valido_no_coincide_con_cantidad`,
   `test_suma_de_entregas_por_linea_distinta_de_cantidad_levanta_error` y
   `test_clave_de_cantidades_por_posicion_fuera_de_rango` se eliminaron de
   `tests/extraccion/test_orden_compra.py` porque prueban lógica que la sección 1 del
   alcance pide sacar por completo (la validación de suma de entregas por renglón).
   `test_validar_override_acumula_errores_de_multiples_problemas_en_un_solo_422` se
   modificó (no se eliminó) para seguir probando "acumula errores de múltiples problemas"
   con los 2 tipos de error que sí sobreviven (cliente + precio_unitario en 2 filas).
