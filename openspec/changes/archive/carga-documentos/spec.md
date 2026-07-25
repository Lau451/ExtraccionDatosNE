# Specification: Carga de documentos

## Archivos

| Archivo | Estado |
|---|---|
| `frontend/src/features/carga-documentos/CargaDocumentos.tsx` | ✅ implementado, sin cambios |
| `frontend/src/features/carga-documentos/components/FormCard.tsx` | ✅ toggle de 3 opciones (OC deshabilitada), cliente, upload — sin selector de clase ni vinculación |
| `frontend/src/features/carga-documentos/components/RecentCard.tsx` | ✅ implementado, campo `proceso_comercial` (puede quedar `null` — se resuelve en `validar-extraccion`, no acá) |
| `frontend/src/features/carga-documentos/components/NuevaLiciCotiDialog.tsx` | ⚠️ sin caller en este change (ver proposal.md) — reservado para `validar-extraccion` |
| `frontend/src/lib/api/extraccion.ts` | ✅ código muerto borrado, `DocumentoReciente.proceso_comercial` (renombrado de `licitacion`), sin `client_id` (columna inexistente en `extraction_results`, bug preexistente encontrado y corregido) |
| `services/extraccion/main.py` (`POST /procesar`) | ✅ `licitacion_id` opcional, validado si viene, NO obligatorio para ningún tipo |
| `services/extraccion/main.py` (`GET /api/documentos`) | ✅ resuelve `proceso_comercial` vía `procesos_comerciales_client.py`, sin `client_id` |
| `services/extraccion/procesos_comerciales_client.py` | ✅ construido, consumido hoy solo por `GET /api/documentos`; `validar-extraccion` lo va a reusar para crear/vincular |
| `services/extraccion/persistent_output.py` | ✅ `proceso_comercial_id` se persiste en `extraction_results` cuando `licitacion_id` viene seteado (antes se descartaba silenciosamente — bug encontrado y corregido) |
| `services/extraccion/routers/licitaciones.py` | ⛔ NO tocado |

## Flujo del formulario (final)

### Toggle de tipo de documento (3 opciones)

| Opción | Label UI | Value interno (`TipoDocumento`) | Estado |
|---|---|---|---|
| Licitación/Directa | "Licitación / Directa" | `'licitaciones'` | habilitada |
| Comparativa | "Comparativa" | `'comparativas'` | habilitada |
| Orden de Compra | "Orden de compra" | `'ordenes'` | **deshabilitada**, badge "Próximamente" |

- MUST deshabilitar la opción "Orden de compra" (no clickeable) y mostrar badge "Próximamente".
  Verificado en Chrome real: el click no cambia el tipo seleccionado.
- MUST impedir que `tipo` tome el valor `'ordenes'` en el estado del formulario.

### Campo Cliente

Sin cambios respecto al estado previo — selector opcional contra `GET /api/clientes`, inyecta
`cliente_id` a `/procesar` para resolución de formato-por-cliente (§8, `_resolver_formato_prompt`).

### Sin selector de vinculación en esta pantalla

Ninguna rama del toggle muestra un selector de `proceso_comercial`. `procesarDocumento()` nunca
envía `licitacionId` desde este formulario. La captura de esa vinculación (y la creación de
procesos nuevos vía "+ Nueva") vive en `validar-extraccion`.

## Backend

### `POST /procesar`

- MUST aceptar `licitacion_id` como parámetro opcional del form (`Form("")`).
- MUST validarlo contra `procesos_comerciales` (vía `procesos_comerciales_client.validar_proceso_comercial_id`)
  SI viene seteado — UUID inválido o inexistente en la droguería → 422 fail-fast (SC-25), ANTES de
  guardar el archivo o llamar a Gemini.
- MUST NOT exigirlo para ningún `tipo` — ni `licitaciones` ni `comparativas`. (Revertido respecto a
  una versión anterior de este spec que sí lo exigía para `comparativas` — ver proposal.md.)
- MUST rechazar (422) `tipo == "ordenes"` explícitamente, fail-fast, antes de cualquier I/O — no
  tiene pipeline implementado.

### `GET /api/documentos`

- MUST devolver el nombre del proceso comercial vinculado a cada documento (cuando existe), sin
  depender de la tabla `licitaciones` — vía `procesos_comerciales_client.listar_nombres_procesos_comerciales()`,
  escopeado por `drogueria_id`.
- MUST NOT romper si el documento no tiene `proceso_comercial_id` — el campo `proceso_comercial`
  del response es `null` en ese caso (será el estado normal para documentos recién subidos desde
  esta pantalla, ya que acá no se captura vinculación).
- MUST NOT incluir `client_id` en el select — la columna no existe en `extraction_results`
  (`docs/schema/extractor_final.sql:371-388`). Bug preexistente (el select original ya lo incluía
  vía el embed roto contra `licitaciones`) encontrado al levantar el servidor real y corregido.

## Scenarios

### Scenario: cargar Licitación/Directa (sin ninguna vinculación posible desde acá)
```
Given: tipo = "licitaciones"
When: POST /procesar sin licitacion_id
Then: 200, se procesa
  AND extraction_results.proceso_comercial_id queda null
```

### Scenario: cargar Comparativa (sin ninguna vinculación posible desde acá)
```
Given: tipo = "comparativas"
When: POST /procesar sin licitacion_id
Then: 200, se procesa — YA NO se rechaza por falta de vinculación
  AND extraction_results.proceso_comercial_id queda null
  AND la vinculación (y la eventual fila en comparativas con su NOT NULL) se resuelve después,
  en la pantalla validar-extraccion
```

### Scenario: Orden de Compra — deshabilitada
```
Given: el usuario ve el toggle de tipo de documento
When: intenta seleccionar "Orden de compra"
Then: la opción está deshabilitada, no responde al click (verificado en Chrome real)
  AND muestra el badge "Próximamente"
```

### Scenario: tipo="ordenes" llega igual al backend (defensa en profundidad)
```
Given: de algún modo llega tipo="ordenes" a POST /procesar (bypass de la UI, por ejemplo)
When: POST /procesar
Then: 422 ANTES de cualquier I/O — "Carga de Orden de Compra todavía no está implementada"
```

### Scenario: licitacion_id inválido — sigue fail-fast (si alguna vez se manda)
```
Given: un caller envía un licitacion_id que no es un UUID válido, o que no existe en
  procesos_comerciales de esta droguería
When: POST /procesar
Then: 422 ANTES de guardar el archivo o llamar a Gemini
```

### Scenario: listar cargas recientes — mayoría sin vincular (esperado)
```
Given: existen documentos procesados desde esta pantalla, ninguno con vinculación (no se captura
  acá)
When: GET /api/documentos
Then: 200
  AND cada documento tiene proceso_comercial: null
  AND ningún campo de la respuesta referencia la tabla licitaciones ni client_id
```

### Scenario: cargas recientes no filtran nombres de otra droguería (si en el futuro sí hay vinculados)
```
Given: un extraction_result tiene proceso_comercial_id de OTRA droguería (no debería pasar, pero
  la función de listado no debe asumirlo)
When: GET /api/documentos
Then: listar_nombres_procesos_comerciales() no encuentra ese id (filtrado por drogueria_id)
  AND el documento se muestra como sin vincular (proceso_comercial: null), nunca con el nombre
  real de un proceso de otra droguería
```
