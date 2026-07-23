# Flujos — Carga de documentos

## 1. Carga de documento end-to-end (selección → validación de tipo → submit multipart → respuesta → refresco de "cargas recientes")

```
Usuario entra a "/" (Sidebar → "Carga de documentos", Sidebar.tsx:13)
        │
        ▼
CargaDocumentos.tsx (CargaDocumentos.tsx:4-16) monta FormCard + RecentCard
        │
        ▼
FormCard.tsx monta:
  - clientesQuery: useQuery(['clientes'], listarClientes) (FormCard.tsx:26)
      → GET /api/clientes (extraccion.ts:33-35, ver casos_de_uso.md)
  - tipo = 'licitaciones' (default, FormCard.tsx:19)
        │
        ▼
Usuario elige tipo (toggle, FormCard.tsx:48-71)
  - Si clickea "Orden de compra": no pasa nada, botón disabled (RN-CARGADOCUMENTOS-001)
  - Si elige "Licitación/Directa" o "Comparativa": setTipo(option.value) (FormCard.tsx:54)
      → accept del <input type="file"> cambia según ACCEPT_POR_TIPO[tipo] (RN-CARGADOCUMENTOS-002)
        │
        ▼
Usuario selecciona/arrastra un archivo
  - Click en la dropzone → <input type="file"> nativo → onChange (FormCard.tsx:102)
  - Drag&drop → onDrop (FormCard.tsx:87-91), sin validar extensión (RN-CARGADOCUMENTOS-002)
        │
        ▼
handleFile(file) (FormCard.tsx:40-43)
  setArchivo(file); mutation.reset() (limpia error/success previos)
        │
        ▼
Usuario elige Cliente (opcional, <select>, FormCard.tsx:118-129) o deja "Sin cliente"
        │
        ▼
Usuario hace submit (botón habilitado solo si hay archivo, RN-CARGADOCUMENTOS-003)
        │
        ▼
mutation.mutate() (FormCard.tsx:77) → mutationFn (FormCard.tsx:29-32)
  procesarDocumento({ archivo, tipo, clienteId: clienteId || undefined })
        │
        ▼
procesarDocumento (extraccion.ts:42-58)
  arma FormData: archivo, tipo, [cliente_id si hay] (licitacion_id NUNCA se agrega desde
  este formulario — ver flujo 2 y decisiones.md D-CARGADOCUMENTOS-002)
        │
        ▼
extraccionFetch('/procesar', { method: 'POST', body: formData }) (client.ts:17-34)
  header Accept: application/json (fuerza respuesta JSON en vez del HTML legacy)
        │
        ├── response.ok === false ──► throw new ApiError(body?.error ?? 'Error N...', status)
        │                              (client.ts:28-31)
        │                                      │
        │                                      ▼
        │                     mutation.isError === true (FormCard.tsx:132-134)
        │                     se muestra (mutation.error as Error).message en rojo
        │
        ▼ (response.ok === true)
mutation.onSuccess (FormCard.tsx:33-37)
  queryClient.invalidateQueries({ queryKey: ['documentos-recientes'] })
  setArchivo(null); fileInputRef.current.value = '' (limpia el input nativo)
        │
        ▼
mutation.isSuccess === true (FormCard.tsx:135-137) → "Documento procesado correctamente."
        │
        ▼
RecentCard.tsx: la invalidación dispara un refetch automático de
  useQuery(['documentos-recientes'], listarDocumentosRecientes) (RecentCard.tsx:12-15)
        │
        ▼
GET /api/documentos (extraccion.ts:37-40, sin filtro `tipo` desde este componente —
  RecentCard.tsx:14 llama listarDocumentosRecientes() sin argumento)
        │
        ▼
RecentCard re-renderiza con las 3 cargas más recientes (data.documentos.slice(0, 3),
  RecentCard.tsx:17), cada una con su badge de estado (STATUS_STYLES, RecentCard.tsx:5-9 —
  ver pendientes.md sobre el mismatch de esos valores con lo que escribe el backend)
```

**Nota de acoplamiento**: `FormCard` y `RecentCard` no se comunican por props ni contexto — el
único vínculo es la key de cache `['documentos-recientes']`, compartida entre la invalidación en
`FormCard.tsx:34` y la query en `RecentCard.tsx:13`. Si algún día cambia el nombre de esa key en un
solo archivo sin el otro, la invalidación deja de refrescar la lista silenciosamente (sin error en
consola, sin tipo que lo detecte). [IMPLEMENTADO] el mecanismo descripto; el riesgo de divergencia
de la key es [SUPOSICIÓN] razonada, no reproducida en runtime en esta sesión.

## 2. Flujo (roto/incompleto) del modal "+ Nueva" licitación/cotización

```
NuevaLiciCotiDialog.tsx existe, exporta NuevaLiciCotiDialog({ clase, onCreated }) completo y
funcional en aislamiento (NuevaLiciCotiDialog.tsx:18-129):
  - Dialog.Trigger renderiza un botón "+ Nueva" (:48-51)
  - Al abrir: formulario con Nombre (siempre) + Apertura/Modalidad (solo si clase === 'licitacion')
  - Al submit: crearProcesoComercial(...) (procesosComerciales.ts:25-33)
      → POST /procesos-comerciales (presupuestacionFetch, presupuestacion.ts:19-41)
      → services/presupuestacion (ver ../procesos_comerciales/api.md)
  - onSuccess: invalida ['procesos-comerciales'], llama onCreated(proceso), cierra el modal
        │
        ▼
PERO: ningún componente de frontend/src/ importa NuevaLiciCotiDialog ──► este flujo NUNCA
se ejecuta en la aplicación real hoy. Confirmado por grep en esta sesión: la única aparición
de "NuevaLiciCotiDialog" en frontend/src/ es su propia definición (línea 18 del propio archivo).
```

El flujo está **completo y correcto de punta a punta como unidad aislada** (el componente en sí no
tiene bugs conocidos), pero **no es alcanzable por ningún usuario** porque no está montado en
ningún árbol de componentes real. Ver [`arquitectura.md`](./arquitectura.md) "Por qué el modal está
huérfano" para la cadena de decisiones que llevó a este estado, y
[`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-001 para la decisión formal de no borrarlo.
