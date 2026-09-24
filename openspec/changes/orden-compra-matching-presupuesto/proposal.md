# Propuesta: Matching de orden de compra contra presupuesto

> Idioma: sigue la convención ya establecida en `openspec/changes/orden-compra/` (proposal.md,
> design.md y los 4 specs están en español, igual que los comentarios del código). Registro
> neutro/profesional.

> **Cambio derivado de `orden-compra`.** Los Tramos 1 (extracción) y 2 (validación) de
> `openspec/changes/orden-compra/` ya están implementados y mergeados a `dev`. Este cambio es la
> fase que sigue inmediatamente a la confirmación de una OC, y **no** es el Tramo 3 (nota de pedido /
> import de retorno de Progress), que sigue diferido y fuera de alcance.

## Intent

Una OC confirmada hoy queda con sus renglones **sin `producto_id`**. D11 del diseño padre lo decidió
a propósito: exigir producto al validar habría bloqueado la digitalización detrás de la calidad del
catálogo. La consecuencia declarada es que `crear_entrega` y el import de retorno hacen `continue` y
**no mueven stock** para esas líneas (`services/presupuestacion/compras/service.py:270-272`).

Eso deja la fase siguiente — la división en entregas — sin base sobre la cual operar: no se puede
planificar ni descontar stock de un renglón que no sabe qué producto es. Falta un paso intermedio
que resuelva `producto_id` por renglón.

El dato que lo resuelve ya existe y es el correcto: **la OC del cliente responde a un presupuesto que
nosotros le cotizamos**. Ese presupuesto ya tiene los renglones resueltos contra nuestro catálogo, así
que el problema no es "adivinar el producto", sino **reconciliar el documento del cliente contra
nuestra propia cotización**, renglón a renglón, y heredar de ahí el producto.

El mecanismo central de esta propuesta **no es hipotético**: se validó end-to-end con datos reales
(cliente SAMCo Rafaela — Hospital Dr. Jaime Ferré, CUIT 30-67428388-8; presupuesto `00246033` cargado
a mano; OC real Nro 00104857 subida por el pipeline real). El join por precio exacto
(`oc_items.precio_unitario = presupuesto_items.precio_unitario`, acotado al cliente) **vinculó los 2
renglones sin ambigüedad**, con cero falsos positivos.

Además, la pantalla de validación hoy es un callejón sin salida: al confirmar navega de vuelta al
listado y el operador no tiene forma de saber que falta un paso. Este cambio cierra ese hueco con el
mismo patrón que ya se aplicó en carga de documentos (subir → navegar a validar).

## Scope

### En alcance

- **Ranking de presupuestos candidatos del cliente**: puntuar cada presupuesto del `cliente_id` ya
  resuelto por cuántos renglones de la OC tienen precio unitario **exacto** contra algún renglón de
  ese presupuesto. El de más coincidencias se sugiere primero; el usuario elige cuál usar.
- **Vínculo renglón a renglón dentro del presupuesto elegido**, con el mismo filtro de precio exacto:
  - un solo match → sugerencia fuerte, **con confirmación humana obligatoria**;
  - más de un match (mismo precio, productos distintos) → desempate por similitud de descripción,
    **reutilizando `rapidfuzz` + `normalizar_descripcion`** (`services/presupuestacion/core/texto.py`,
    ya en uso por `matching/service.py`), presentado como lista ordenada para que el usuario elija;
  - sin match → el renglón queda **`pendiente`** y **no bloquea** al resto.
- **Herencia de `producto_id`**: confirmar un vínculo copia el `producto_id` del lado del presupuesto
  al renglón de la OC.
- **Relación N:1 permitida con aviso**: un renglón de presupuesto puede quedar vinculado desde más de
  un renglón de OC (el cliente puede partir en su documento lo que se cotizó como una sola línea). No
  se bloquea; se avisa de forma **suave y no bloqueante** cuando el mismo renglón de presupuesto se
  reutiliza.
- **Esquema nuevo para el vínculo, del lado de `oc_items`**: alguna forma de registrar el vínculo y
  su estado (sugerido / confirmado / pendiente). La forma exacta la resuelve la fase de diseño.
- **Pantalla de matching de dos columnas**: presupuesto elegido a la izquierda
  (descripción/cantidad/precio/estado de vínculo), OC a la derecha (cada renglón con su estado). Click
  en un renglón de OC resalta el o los candidatos del lado del presupuesto. **Confirmación granular
  por renglón con un click**, no un "guardar todo" al final — mismo patrón que `OrdenCompraSelector`.
- **Navegación automática**: confirmar la validación de una OC navega inmediatamente a la pantalla de
  matching de **esa misma OC**, en lugar de volver al listado. Requiere que
  `ResultadoValidarExtraccion` exponga el `orden_compra_id` creado, que hoy no devuelve.

### Fuera de alcance

- **El import de presupuestos legados** desde Progress. Su diseño ya está acordado en otra sesión y
  está frenado esperando que Sistemas confirme dónde deja Progress los archivos. Ver § Dependencies:
  **no bloquea este cambio**.
- **Entregas (división en entregas)**. Este cambio resuelve `producto_id` por renglón y nada más. Qué
  ocurre después del matching es una fase futura, todavía sin diseñar.
- **Tramo 3** (nota de pedido saliente / import del CSV de retorno de Progress). Sigue diferido en la
  propuesta padre, sin cambios.
- **El motor de matching de productos contra catálogo** (`procesar_matching_item`,
  `services/presupuestacion/matching/service.py`). Es un concepto distinto: matchea descripciones de
  `items_proceso` contra `productos`. **No se toca.** De ese módulo solo se reutilizan las piezas de
  texto/similitud (`normalizar_descripcion`, `rapidfuzz`), no su flujo.
- **`items_proceso.estado_matching` / `items_proceso.confianza_matching`**. Pertenecen a ese motor,
  que hoy no está en uso: todos los presupuestos van a venir del import legado, que no lo corre. Esos
  campos quedan vacíos y **este cambio no los escribe ni los lee**.
- **Auto-confirmación de vínculos.** Ningún vínculo se aplica sin un click humano, en ningún nivel de
  confianza — mismo invariante duro que D3 ya impone para la resolución de cliente.
- Tolerancia de precio. Es exacto, sin margen, por decisión explícita de producto: "es el mismo que
  se cotizó".

## Capabilities

### Nuevas capacidades

- `oc-presupuesto-candidato`: listar los presupuestos del cliente de una OC confirmada, puntuarlos por
  coincidencia exacta de precio unitario contra los renglones de la OC, y dejar que el usuario elija
  cuál usar.
- `oc-presupuesto-vinculacion`: vincular renglón de OC ↔ renglón de presupuesto dentro del presupuesto
  elegido (sugerencia por precio exacto, desempate por similitud de descripción, confirmación humana
  puntual, estado `pendiente` sin bloqueo, N:1 con aviso) y heredar `producto_id` al confirmar.

### Capacidades modificadas

- `orden-compra-validacion`: confirmar una OC deja de terminar en el listado; navega a la pantalla de
  matching de esa OC, y el resultado de la validación expone el `orden_compra_id`.

  > **Nota de reconciliación**: esta capacidad **todavía no está archivada** — su spec vive en
  > `openspec/changes/orden-compra/specs/orden-compra-validacion/spec.md`, no en `openspec/specs/`.
  > El delta de esta propuesta debe reconciliarse contra ese archivo cuando `orden-compra` se archive,
  > no contra `openspec/specs/` (donde hoy solo hay `terceros`, `catalogos-comerciales`, `contactos`,
  > `direcciones`, `imports` y la familia `pcp-*`, ninguna afectada por este cambio).

## Approach

**El precio es la clave de join, la descripción es solo el desempate, y el humano es siempre la
compuerta.** Ese es el orden de autoridad de todo el mecanismo, y es el que se validó con datos
reales.

1. **Encontrar el presupuesto.** El `cliente_id` ya viene resuelto y confirmado por un humano en la
   validación (D3 del cambio padre). Sobre los presupuestos de ese cliente se corre el mismo join de
   precio exacto y se cuenta cuántos renglones de la OC matchean contra cada uno. El de puntaje más
   alto se sugiere primero. El precio vive en `presupuesto_items.precio_unitario` — **confirmado
   contra el esquema real**: `items_proceso` no tiene columna de precio, solo `monto_estimado`.
2. **Vincular dentro del presupuesto elegido.** Mismo filtro de precio exacto por renglón. Un match
   único es una sugerencia fuerte, nunca una escritura automática. Varios matches con el mismo precio
   se ordenan por `fuzz.WRatio` sobre `normalizar_descripcion(...)` — la misma maquinaria que ya usa
   `_generar_candidatos` en `matching/service.py:17-36`, sin reimplementar nada y sin llamar a
   `procesar_matching_item` (que está acoplado a `items_proceso` y al catálogo de productos).
3. **Confirmar hereda.** El click de confirmación escribe el vínculo y copia el `producto_id` del
   renglón del presupuesto al `oc_items.producto_id`. Un renglón sin match queda `pendiente`: la OC
   avanza igual, con la ausencia **visible** en vez de silenciosa — la misma lógica que D11 ya aplicó
   a `renglones_sin_producto`.
4. **Estado propio, del lado de la OC.** El vínculo necesita esquema nuevo porque no hay dónde
   guardarlo: `items_proceso.estado_matching`/`confianza_matching` pertenecen a otro motor y quedan
   fuera. La forma probable es una FK nullable en `oc_items` hacia `items_proceso`, pero el soporte
   limpio de N:1 puede requerir una tabla puente — **decisión de la fase de diseño**, no de esta
   propuesta.
5. **La pantalla es la misma compuerta de siempre.** Dos columnas, click para resaltar, click para
   confirmar, renglón por renglón. Se llega a ella automáticamente al confirmar la validación, igual
   que hoy se llega a validación automáticamente después de subir el documento.

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `services/presupuestacion/compras/` | Nuevo | Servicio + repository del matching OC↔presupuesto: ranking de presupuestos candidatos, sugerencia de vínculos, confirmación. Ubicación exacta del módulo (¿acá o módulo propio?) a decidir en diseño |
| `services/presupuestacion/presupuestos/repository.py` | Modificado | Falta una consulta "presupuestos de un cliente": hoy solo hay lookups por `presupuesto_id` (`buscar_presupuesto`, `listar_items_presupuesto`). `listar_items_presupuesto` se reutiliza sin cambios |
| `services/presupuestacion/matching/service.py` | **Sin cambios** | Se reutiliza el patrón `process.extract` + `fuzz.WRatio`, no el flujo. `procesar_matching_item` no se llama ni se modifica |
| `services/presupuestacion/core/texto.py` | **Sin cambios** | `normalizar_descripcion` se reutiliza tal cual para el desempate |
| `services/presupuestacion/extraccion/models.py` | Modificado | `ResultadoValidarExtraccion` gana `orden_compra_id: str \| None` (campo aditivo; hoy devuelve solo `extraction_id`, `document_type`, `proceso_comercial_id`, `filas_creadas`, `comparativa_id`, `reemplazo_version_anterior`) |
| `services/presupuestacion/extraccion/service.py` | Modificado | `_materializar_orden_compra()` debe propagar hacia arriba el id de la OC creada |
| `supabase/migrations/00XX_*.sql` | Nuevo | Esquema del vínculo OC↔presupuesto + RLS y GRANTs si resulta ser una tabla nueva (convención del proyecto: `mismo_tenant(drogueria_id)` + `get_rol()`) |
| `docs/schema/extractor_final.sql` | Modificado | Reflejar el esquema nuevo. **Verificar contra la base viva antes de migrar**: el snapshot ya se comprobó desactualizado para `clientes` y `ordenes_compra` (C1/C4 del diseño padre) |
| `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.tsx` | Modificado | El `onSuccess` de la mutación (líneas 81-85) hoy invalida queries y hace `navigate({ to: '/validar-extraccion' })`; pasa a navegar a la pantalla de matching de la OC recién creada |
| `frontend/src/lib/api/extracciones.ts` | Modificado | Espejo del campo nuevo en la interfaz `ResultadoValidarExtraccion` |
| `frontend/src/features/oc-matching/` (nombre tentativo) | Nuevo | Pantalla de dos columnas + componentes de sugerencia/confirmación por renglón |
| `frontend/src/routes/` + `routeTree.gen.ts` | Nuevo/Generado | Ruta nueva parametrizada por orden de compra |
| `frontend/src/lib/api/` | Nuevo | Cliente HTTP de los endpoints de matching |
| `tests/` (backend) + `*.test.tsx` (frontend) | Nuevo | Tests RED primero (`strict_tdd: true` en `openspec/config.yaml`) para ranking, desempate, N:1, pendiente y navegación |

## Risks

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| **El import legado no resuelve `producto_id` en `items_proceso`** — el import de PCP, que es el mismo patrón que se va a reusar, **nunca** lo resuelve; el gap ya está documentado ahí. Si se repite, el matching no tiene producto que heredar en absoluto | Alta | Riesgo **real y no resuelto**. La pantalla debe mostrar explícitamente cuándo el renglón del presupuesto no tiene producto, en vez de confirmar un vínculo que no hereda nada. Qué hacer en ese caso (¿bloquear el vínculo? ¿permitirlo vacío?) es Open Question #5 |
| No hay presupuestos cargados para el cliente, por el bloqueo del import legado | Media | La pantalla muestra un estado "sin presupuestos para este cliente" explícito, no un error. **La carga manual de un presupuesto ya está probada** y es camino válido, no solo de desarrollo. Ver § Dependencies |
| El precio exacto sin tolerancia no matchea por diferencias de redondeo, IVA o moneda entre el documento del cliente y nuestro presupuesto | Media | El renglón cae a `pendiente`, nunca a un vínculo incorrecto. El desempate por descripción y la elección manual siguen disponibles. La tolerancia se descartó por decisión explícita de producto |
| Falso positivo por precio compartido entre productos distintos (precios redondos tipo $100,00 en catálogos grandes) | Media | El precio nunca escribe solo: un empate produce **lista de candidatos**, no un vínculo. La confirmación humana es obligatoria en todos los casos |
| N:1 sin control sobre-compromete un renglón cotizado (se vincula más cantidad de la que se presupuestó) | Media | Aviso suave y no bloqueante cuando un renglón de presupuesto ya está vinculado, mostrando cuántas veces. No se bloquea por decisión explícita: el caso de negocio (el cliente parte una línea) es legítimo |
| `ResultadoValidarExtraccion` es un contrato compartido por las tres rutas de documento (licitación, comparativa, OC) | Baja | Campo aditivo y nullable; `null` para las otras dos rutas. No cambia ningún campo existente |
| La pantalla nueva se convierte en otro callejón sin salida si el operador no puede volver a ella | Baja | Open Question #7: debe haber re-entrada desde el listado de OC, no solo la navegación automática |

## Rollback Plan

El backend y el frontend son **aditivos**: revertir el commit deja la OC exactamente como está hoy
(renglones sin `producto_id`, confirmación navegando al listado). Ningún flujo existente lee el
vínculo nuevo ni el campo `orden_compra_id`.

1. **Revertir frontend primero.** Quitar la ruta nueva y restaurar
   `navigate({ to: '/validar-extraccion' })` en el `onSuccess`. A partir de ese punto nadie puede
   crear vínculos nuevos.
2. **Revertir backend.** Quitar los endpoints y el servicio de matching. El campo `orden_compra_id`
   del resultado puede quedarse sin daño (es aditivo y nullable); quitarlo es opcional.
3. **Datos antes que esquema.** Si el vínculo quedó como FK en `oc_items`, hay que ponerla en `NULL`
   antes de dropear la columna. Si quedó como tabla puente, se dropea la tabla entera con su RLS.
   **Los `oc_items.producto_id` ya heredados son datos de negocio legítimos y NO se revierten**: son
   exactamente el mismo valor que un operador podría haber cargado a mano, y borrarlos destruiría
   trabajo real. El rollback quita el mecanismo, no su resultado.

## Dependencies

- **Presupuestos cargados para el cliente.** Encontrar un presupuesto contra el cual matchear exige
  filas en `presupuestos` / `items_proceso` / `presupuesto_items` para ese cliente.
- **El import de presupuestos legados está bloqueado**, esperando que Sistemas confirme dónde deja
  Progress los archivos de export. **Esto NO bloquea construir ni testear este cambio**: ya se
  demostró end-to-end que un presupuesto se puede cargar a mano siguiendo el mismo mapeo de columnas
  acordado para el import legado, y **ese camino sigue siendo válido en producción** — la carga manual
  es un fallback legítimo del negocio, no solo un atajo de desarrollo. El import legado es un cambio
  separado, ya diseñado en otro lado, y **no es problema de esta propuesta**.
- **`rapidfuzz`** ya es dependencia del proyecto (`services/presupuestacion/matching/service.py:4`).
  No se agrega nada a `requirements.txt`.
- **El cambio padre `orden-compra` (Tramos 1 y 2) debe estar en `dev`** — ya lo está. Este cambio
  asume `ordenes_compra`/`oc_items` poblados con `cliente_id` resuelto.

## Success Criteria

- [ ] Confirmar la validación de una OC navega automáticamente a la pantalla de matching de **esa**
      OC, sin pasar por el listado.
- [ ] Dada una OC de un cliente con varios presupuestos, el presupuesto con más coincidencias exactas
      de precio aparece primero en la lista de candidatos.
- [ ] Un renglón de OC con un único match de precio exacto se muestra como sugerido y **no queda
      vinculado hasta el click de confirmación**.
- [ ] Un renglón de OC con varios matches del mismo precio muestra una lista ordenada por similitud de
      descripción, sin preseleccionar ninguno.
- [ ] Un renglón de OC sin ningún match queda `pendiente` y **no impide** confirmar los demás
      renglones de la misma OC.
- [ ] Confirmar un vínculo escribe `oc_items.producto_id` con el producto del renglón del presupuesto.
- [ ] Vincular dos renglones de OC al mismo renglón de presupuesto **se permite** y muestra un aviso
      no bloqueante.
- [ ] `items_proceso.estado_matching` y `items_proceso.confianza_matching` quedan **sin modificar**
      después de una sesión completa de matching.
- [ ] El caso real ya validado (OC 00104857 ↔ presupuesto 00246033 de SAMCo Rafaela) se reproduce como
      test: 2 renglones, 2 vínculos correctos, cero ambigüedad.

## Open Questions (diferidas a spec/design)

1. **Esquema exacto del vínculo.** ¿FK nullable en `oc_items` hacia `items_proceso`? ¿Hacia
   `presupuesto_items`? ¿Tabla puente? Y dónde vive el estado (`sugerido`/`confirmado`/`pendiente`) y
   la confianza del desempate.
2. **¿La relación N:1 obliga a tabla puente?** Una FK simple en `oc_items` soporta N:1 de forma
   natural (N renglones de OC apuntando a la misma fila de presupuesto); una tabla puente solo hace
   falta si además hay que soportar 1:N o M:N, que hoy nadie pidió. Verificar antes de agregar una
   tabla.
3. **Cómo se listan los presupuestos del cliente antes de rankearlos**: ¿todos? ¿filtrados por estado?
   ¿por ventana de fecha respecto de la `fecha_emision` de la OC? ¿con un tope de candidatos?
4. **Umbral y corte del desempate por descripción**: qué score mínimo hace que un candidato se muestre
   y cuántos se muestran. `matching/service.py` usa `_UMBRAL_SUGERIDO = 70` y `_TOP_K = 5` para otro
   problema — no se hereda sin justificarlo.
5. **Qué pasa si el renglón del presupuesto no tiene `producto_id`** (riesgo del import legado):
   ¿se bloquea el vínculo, o se permite vincular sin heredar y se marca visiblemente?
6. **¿Se puede deshacer un vínculo confirmado?** Y si se deshace, ¿qué pasa con el `producto_id` ya
   heredado en `oc_items`?
7. **Re-entrada a la pantalla.** ¿Se llega solo por la navegación automática, o también desde el
   listado de OC? Sin re-entrada, una sesión interrumpida no se puede retomar.
8. **¿El estado de matching de la OC condiciona la fase futura de entregas?** Si quedan renglones
   `pendiente`, ¿la OC puede pasar igual a entregas (con las líneas sin stock, como hoy) o hay un
   gate? Se puede diferir, pero conviene no cerrar la puerta con el esquema.
9. **Ubicación del módulo backend**: ¿dentro de `services/presupuestacion/compras/` (donde viven
   `ordenes_compra`/`oc_items`) o módulo propio? Meterlo en `matching/` sería confuso: ese nombre ya
   está tomado por el motor de catálogo, que es otro concepto.
10. **Roles.** Probablemente `_ROLES_VALIDAR` (`extraccion/router.py:23`), por el mismo criterio de
    D12 ("escribe quien valida"), pero hay que confirmarlo contra el código en lugar de asumirlo.

**Nota de verificación**: el mecanismo central (ranking y vínculo por precio exacto) está verificado
contra el esquema real del proyecto Supabase de test `grnamollopxdlstcpxhc` y validado end-to-end con
datos reales. Lo que queda abierto es **cómo se persiste el vínculo**, no **si el vínculo se puede
encontrar**.
