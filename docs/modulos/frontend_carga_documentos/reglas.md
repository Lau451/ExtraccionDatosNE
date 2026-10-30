# Reglas — Carga de documentos

Numeración RN-CARGADOCUMENTOS-NNN. Se documentan solo las reglas verificadas contra el código; no
se infla la lista con comportamiento genérico de HTML/React que no sea una decisión del módulo.

### RN-CARGADOCUMENTOS-001 — Tres tipos de documento; licitación y directa se suben igual

- **Regla**: el toggle de tipo de documento ofrece 3 opciones (`TIPO_OPTIONS`, `FormCard.tsx`):
  "Licitación / Directa" (`'licitaciones'`), "Comparativa" (`'comparativas'`) y "Orden de compra"
  (`'ordenes'`). No hay tipo preseleccionado (presupuestador-v1 T1b): hasta que el usuario elige
  uno, el área de archivo está deshabilitada, muestra "Elegí el tipo de documento para continuar"
  y "Procesar" no se puede usar.
- **Licitación o directa** (presupuestador-v1 T2a): la carga no elige la clase. `POST /procesar`
  guarda todo `tipo` que no sea comparativa ni orden de compra como `document_type='licitacion'`
  (`services/extraccion/main.py`), con el robot genérico. La clase (licitación o directa), el
  cliente y el nombre del proceso comercial se eligen al validar. Las directas subidas antes con
  `document_type='cotizacion'` siguen siendo válidas.
- **Cliente**: el selector de cliente (opcional) solo aparece para comparativas y órdenes de
  compra, donde elige el formato de prompt del cliente (`cliente_formato_documentos`). Licitaciones
  y directas usan siempre el prompt genérico y no envían `cliente_id`.
- [IMPLEMENTADO]

### RN-CARGADOCUMENTOS-002 — Extensiones de archivo aceptadas, distintas por tipo de documento

- **Regla**: `ACCEPT_POR_TIPO` (`FormCard.tsx:12-16`) fija el atributo `accept` del `<input
  type="file">` (`FormCard.tsx:101`) según el tipo seleccionado:

  | Tipo | Extensiones aceptadas |
  |---|---|
  | `licitaciones` | `.pdf,.jpg,.jpeg,.png,.xls,.xlsx` |
  | `ordenes` | `.pdf,.jpg,.jpeg,.png,.xls,.xlsx` |
  | `comparativas` | `.pdf,.jpg,.jpeg,.png,.xls,.xlsx,.ods,.html,.htm` (agrega `.ods`, `.html`, `.htm` respecto al resto) |

- **Consecuencia**: el atributo `accept` de HTML es solo una sugerencia al selector de archivos del
  sistema operativo/navegador — no bloquea de forma confiable un archivo de otra extensión
  arrastrado y soltado directamente (`handleFile`, `FormCard.tsx:40-43`, no valida la extensión del
  `File` recibido antes de guardarlo en estado). No hay ninguna validación de extensión en
  JavaScript antes del submit; la validación real de tipo de archivo, si existe, ocurre del lado de
  `services/extraccion` (fuera del alcance de archivos de esta documentación).
- [IMPLEMENTADO] la definición de `ACCEPT_POR_TIPO` y su uso en el input; [SUPOSICIÓN] razonada que
  el drag&drop no valida extensión — confirmado leyendo `handleFile`, no se encontró ninguna
  comprobación de `file.name`/`file.type` en ese código.

### RN-CARGADOCUMENTOS-003 — El submit requiere un archivo seleccionado

- **Regla**: el botón de submit está deshabilitado si no hay `archivo` en estado o si la mutación
  está en curso (`disabled={!archivo || mutation.isPending}`, `FormCard.tsx:141`). Como defensa
  adicional, `mutationFn` también lanza si se invoca sin archivo (`if (!archivo) throw new
  Error('Falta seleccionar un archivo')`, `FormCard.tsx:30`), aunque ese camino no debería
  alcanzarse normalmente porque el botón ya está deshabilitado en ese estado.
- [IMPLEMENTADO]

### RN-CARGADOCUMENTOS-004 — El cliente es opcional y solo se envía si fue seleccionado

- **Regla**: el `<select>` de cliente tiene una opción "Sin cliente" con `value=""` por defecto
  (`FormCard.tsx:123`); al construir el payload de `procesarDocumento`, `clienteId` se convierte
  explícitamente a `undefined` si está vacío (`clienteId: clienteId || undefined`,
  `FormCard.tsx:31`), de modo que el campo `cliente_id` del `FormData` solo se agrega si hay un
  valor real (`procesarDocumento`, `extraccion.ts:51`, `if (clienteId) formData.append('cliente_id',
  clienteId)`).
- [IMPLEMENTADO]

### RN-CARGADOCUMENTOS-005 — Sin validación de esquema propia: solo la nativa del navegador

- **Regla**: no hay ninguna librería de validación de esquema (`zod` u otra) en
  `frontend/package.json` (confirmado en esta sesión: ni en `dependencies` ni en `devDependencies`)
  ni en el código de este módulo. La única validación del formulario de carga es el `disabled` del
  botón de submit (RN-CARGADOCUMENTOS-003) y el `accept` del input de archivo
  (RN-CARGADOCUMENTOS-002, que no bloquea drag&drop). El formulario del modal huérfano
  (`NuevaLiciCotiDialog.tsx`) sí usa `required` en el campo "Nombre" (`:71`), consistente con el
  mismo patrón de validación nativa HTML5 que ya se documentó en
  [`../frontend_login/reglas.md`](../frontend_login/reglas.md) RN-LOGIN-001.
- [IMPLEMENTADO]

## Regla conocida por un componente de UI vía comentario: `ck_proc_cotizacion_sin_seguimiento`

`NuevaLiciCotiDialog.tsx:31-33` incluye un comentario que referencia directamente una constraint
SQL del backend, dentro del código que arma el payload de `crearProcesoComercial`:

```typescript
// El backend rechaza apertura/modalidad para clase=cotizacion (constraint
// ck_proc_cotizacion_sin_seguimiento) — solo se mandan si es licitación.
...(esLicitacion && apertura ? { apertura } : {}),
...(esLicitacion ? { modalidad } : {}),
```

Esa misma constraint ya está documentada desde el lado del backend como
[`../procesos_comerciales/reglas.md`](../procesos_comerciales/reglas.md) RN-PROCESOS-001 ("Una
cotización no admite campos de seguimiento formal de licitación"), con la cita textual completa del
comentario de origen en `services/presupuestacion/procesos_comerciales/service.py:13-16`. No se
numera como una regla nueva de este módulo (RN-CARGADOCUMENTOS-NNN) porque no es una regla que este
módulo defina — es una regla del backend que un componente de UI de este módulo conoce y replica
por comodidad de UX (evitar un round-trip con 422 para el caso más común), sin que el backend deje
de validarla igual del lado servidor. Se documenta acá como referencia cruzada explícita entre
ambos lados. Ver [`decisiones.md`](./decisiones.md) para el riesgo de que ambas copias diverjan.
