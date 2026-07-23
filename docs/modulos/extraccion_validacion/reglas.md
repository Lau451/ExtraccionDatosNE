# Reglas de negocio — Extracción-Validación

## RN-EXTRACCIONVALIDACION-001 — Branching por `document_type` [IMPLEMENTADO]

`validar_extraccion` decide la materialización únicamente por
`extraction["document_type"]` (`service.py:266,270-289`):

- `"licitacion"` o `"cotizacion"` (constante `_TIPOS_ITEMS_PROCESO`, `service.py:19`)
  → `_materializar_licitacion`: crea `items_proceso` y dispara matching automático.
- `"comparativa"` → `_materializar_comparativa`: crea `comparativas` + `ofertas_items`.
- Cualquier otro valor → `ValidationError` (ver RN-EXTRACCIONVALIDACION-002).

`licitacion` y `cotizacion` comparten la misma rama porque "mismo robot de extracción
para ambos hoy — la distinción cotizacion/licitacion vive en
`procesos_comerciales.clase`, no acá" (comentario textual, `service.py:17-18`).

## RN-EXTRACCIONVALIDACION-002 — `orden_compra` no tiene materialización implementada [IMPLEMENTADO]

`document_type` admite 4 valores (`DocumentType`, `models.py:5`:
`"comparativa" | "licitacion" | "cotizacion" | "orden_compra"`), pero solo 3 tienen
rama de materialización. Si `document_type == "orden_compra"` (o cualquier valor no
contemplado), `validar_extraccion` levanta:

```python
raise ValidationError(
    f"document_type='{document_type}' todavía no tiene materialización implementada"
)
```

(`service.py:286-289`, rama `else` del branching). Confirmado por test:
`test_validar_orden_compra_no_implementado` (`tests/extraccion/test_service.py:172-189`).

## RN-EXTRACCIONVALIDACION-003 — Una extracción no puede validarse dos veces [IMPLEMENTADO]

Si `extraction["validado"]` ya es `True`, `validar_extraccion` levanta
`ConflictError("Esta extracción ya fue validada")` antes de intentar ninguna
materialización (`service.py:254-255`). Confirmado por test:
`test_validar_ya_validada_levanta_conflict` (`tests/extraccion/test_service.py:61-84`).

## RN-EXTRACCIONVALIDACION-004 — Resolución de `proceso_comercial_id` [IMPLEMENTADO]

`_resolver_proceso_comercial_id` (`service.py:29-58`) aplica, en orden:

1. Si la extracción **ya** tiene `proceso_comercial_id`:
   - Si además se indicó uno por parámetro y **difiere** del existente →
     `ConflictError("Esta extracción ya está vinculada a otro proceso_comercial_id")`
     (`service.py:35-37`).
   - Si coincide o no se indicó ninguno → se usa el existente, sin volver a escribir
     nada (`service.py:38`).
2. Si la extracción **no** tiene `proceso_comercial_id`:
   - Si tampoco se indicó uno por parámetro →
     `ValidationError("Esta extracción no tiene proceso_comercial_id — indicalo para
     poder validarla")` (`service.py:41-43`).
   - Si se indicó uno pero no existe → `NotFoundError("No se encontró el proceso
     comercial indicado")` (`service.py:46-47`).
   - Si existe pero pertenece a otra droguería → `ValidationError("El proceso
     comercial indicado no pertenece a la misma droguería que la extracción")`
     (`service.py:48-51`).
   - Si pasa las tres validaciones → se persiste el vínculo (`UPDATE
     extraction_results.proceso_comercial_id`, `service.py:53-57`) y se retorna.

Confirmado por 4 tests: `test_validar_sin_proceso_comercial_id_exige_indicarlo`,
`test_validar_con_proceso_comercial_id_de_otra_drogueria_falla`,
`test_validar_no_pisa_proceso_comercial_id_ya_vinculado`
(`tests/extraccion/test_service.py:87-169`).

## RN-EXTRACCIONVALIDACION-005 — `es_drogueria_propia` no se auto-detecta [IMPLEMENTADO]

Toda fila de `ofertas_items` creada desde una comparativa se inserta con
`"es_drogueria_propia": False` fijo (`service.py:220`), sin importar el texto de
`fila["proveedor"]`. Ver [`decisiones.md`](./decisiones.md) D-EXTRACCIONVALIDACION-001
para el motivo.

## RN-EXTRACCIONVALIDACION-006 — Workaround: `marca` del CSV reusada como `descripcion` [IMPLEMENTADO]

`ofertas_items.descripcion` se llena con `(fila.get("marca") or "").strip() or None`
(`service.py:216-219`), porque "no hay columna 'marca' en `ofertas_items` ni
'descripcion' en el CSV de comparativa: reusamos marca como descripcion (mejor que
perderla)" (comentario textual, `service.py:216-218`). Ver
[`decisiones.md`](./decisiones.md) D-EXTRACCIONVALIDACION-002.

## RN-EXTRACCIONVALIDACION-007 — Versionado de comparativas: solo una vigente por proceso [IMPLEMENTADO]

Antes de crear una comparativa, `_materializar_comparativa` busca si ya existe una
vigente para el mismo `proceso_comercial_id` (`buscar_comparativa_vigente`,
`service.py:154`). Si existe:

- La nueva comparativa se crea con `version_numero = vigente_previa["version_numero"]
  + 1`, `reemplaza_id = vigente_previa["id"]` y `motivo_version = "nueva extracción
  validada"` (`service.py:167-170`).
- La comparativa anterior se invalida (`es_vigente = False`,
  `repository.py:68-69`, llamado en `service.py:184`).
- Se dispara notificación a roles `admin`/`gerencia`/`lider_comercial` (ver
  RN-EXTRACCIONVALIDACION-012).

Si no existe una vigente previa, se crea con los valores por defecto del schema
(`version_numero=1`, `es_vigente=TRUE`, sin `reemplaza_id`/`motivo_version`).
Confirmado por test: `test_validar_comparativa_segunda_vez_versiona_y_notifica`
(`tests/extraccion/test_service.py:301-375`).

## RN-EXTRACCIONVALIDACION-008 — Cálculo de `posicion_precio` y `adjudicacion_estimada` [IMPLEMENTADO]

`_computar_posiciones` (`service.py:96-109`) agrupa las ofertas creadas por
`renglon_id`, ordena cada grupo por `precio_unitario` ascendente
(`Decimal(str(f["precio_unitario"]))`, `service.py:106`) y asigna
`posicion_precio` correlativo empezando en 1; la fila con `posicion_precio == 1` (la
más barata del renglón) recibe `adjudicacion_estimada = True`, el resto `False`
(`service.py:107-108`). El docstring de la función referencia "(§5)" como sección de
un documento de especificación externo no presente en este repositorio — no se pudo
verificar su contenido en esta sesión.

Confirmado por test:
`test_validar_comparativa_calcula_posicion_precio_y_adjudicacion_estimada`
(`tests/extraccion/test_service.py:203-255`).

## RN-EXTRACCIONVALIDACION-009 — Vínculo de oferta a `item_proceso` por número de renglón [IMPLEMENTADO]

Al materializar una comparativa, cada oferta intenta vincularse a un
`items_proceso.id` ya existente para el mismo `proceso_comercial_id`, buscando por
`numero_renglon == int(fila["renglon"].strip())` (`service.py:203-207`). Si el texto
del renglón no es un entero válido (`ValueError`) o no hay `item_proceso` con ese
número, `item_proceso_id` queda en `None` (`service.py:207,213`) — no es un error,
la fila de oferta se crea igual. Confirmado por test:
`test_validar_comparativa_linkea_item_proceso_id_por_numero_renglon`
(`tests/extraccion/test_service.py:258-298`).

## RN-EXTRACCIONVALIDACION-010 — El router valida pertenencia de droguería antes de delegar [IMPLEMENTADO]

`router.py:22-34` hace un `SELECT id, drogueria_id` sobre `extraction_results` con
`user_client` (RLS-aware) **antes** de llamar a `validar_extraccion_para_endpoint`
(que corre con `service_role`, sin RLS). Si no se encuentra la extracción →
`NotFoundError`; si el usuario no es `superadmin` y la extracción pertenece a otra
droguería → `ForbiddenError("La extracción no pertenece a tu droguería")`
(`router.py:33-34`). Esta validación es responsabilidad exclusiva del router — el
service (`validar_extraccion`) no vuelve a chequear pertenencia de droguería del
llamante, solo la del `proceso_comercial_id` indicado contra la extracción
(RN-EXTRACCIONVALIDACION-004).

## RN-EXTRACCIONVALIDACION-011 — Roles habilitados para validar [IMPLEMENTADO]

`POST /extracciones/{extraction_id}/validar` requiere uno de `admin`, `gerencia`,
`lider_comercial`, `comercial` (`_ROLES_VALIDAR`, `router.py:12`, aplicado vía
`require_roles(*_ROLES_VALIDAR)`, `router.py:19`).

## RN-EXTRACCIONVALIDACION-012 — Roles notificados en un reemplazo de comparativa [IMPLEMENTADO]

Solo `admin`, `gerencia`, `lider_comercial` (`_ROLES_NOTIFICACION_REEMPLAZO`,
`service.py:21`) reciben la notificación de reemplazo — **no** incluye `comercial`,
pese a que ese rol sí puede ejecutar la validación (RN-EXTRACCIONVALIDACION-011).
Motivo pendiente de definición funcional.
