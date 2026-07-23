# Casos de uso — Carga de documentos

## Endpoints consumidos por componente

| Componente | Función frontend | Método/Path | Backend | Evidencia | Contrato completo |
|---|---|---|---|---|---|
| `FormCard.tsx` | `listarClientes` | `GET /api/clientes` | `services/extraccion` | `FormCard.tsx:26` (`useQuery(['clientes'], listarClientes)`) → `extraccion.ts:33-35` | [`../extraccion_api/api.md`](../extraccion_api/api.md) `routers/clientes.py`; [`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md) fila `GET /api/clientes` |
| `FormCard.tsx` | `procesarDocumento` | `POST /procesar` (multipart) | `services/extraccion` | `FormCard.tsx:31` (`mutationFn`) → `extraccion.ts:42-58` | [`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md) sección "`POST /procesar`" — confirma `extraccion.ts:42-58` como consumidor del frontend nuevo |
| `RecentCard.tsx` | `listarDocumentosRecientes` | `GET /api/documentos?tipo=` | `services/extraccion` | `RecentCard.tsx:14` (`useQuery(['documentos-recientes'], () => listarDocumentosRecientes())`, sin argumento → sin filtro `tipo`) → `extraccion.ts:37-40` | [`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md) tabla "`GET /api/documentos` y derivados", fila `GET /api/documentos?tipo=` |
| `NuevaLiciCotiDialog.tsx` (**huérfano, sin caller — ver `README.md`**) | `crearProcesoComercial` | `POST /procesos-comerciales` | `services/presupuestacion` | `NuevaLiciCotiDialog.tsx:29-36` (`mutationFn`) → `procesosComerciales.ts:25-33` | [`../procesos_comerciales/api.md`](../procesos_comerciales/api.md) fila `POST /procesos-comerciales` — roles requeridos `_ROLES_ESCRITURA` (`admin`, `gerencia`, `lider_comercial`, `comercial`), valida RN-PROCESOS-001 |

Ningún otro endpoint de `services/extraccion` ni `services/presupuestacion` es consumido por los
componentes en el alcance de esta documentación. En particular, no se encontró consumidor en este
módulo (ni en el resto de `frontend/src/`, según el grep de la sesión previa que documentó
[`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md)) para
`GET /api/documentos/{doc_id}`, `GET /api/documentos/{doc_id}/descargar`, ni ningún endpoint de
`routers/licitaciones.py` o `routers/extraction_results.py`.

## `POST /procesos-comerciales` — dependencia indirecta y no ejercitada hoy

La fila de `NuevaLiciCotiDialog.tsx` en la tabla de arriba documenta el código tal como está escrito
(qué endpoint llamaría si se montara), no un flujo real ejecutable hoy: como el componente no tiene
ningún caller (ver [`README.md`](./README.md) y [`flujo.md`](./flujo.md) #2), este endpoint nunca
se invoca desde la aplicación actual a través de este módulo. Se documenta acá porque es la única
vía por la que este módulo depende de `services/presupuestacion`, y para que quien reactive el
componente en `validar-extraccion` tenga el contrato de referencia sin tener que releer el código
del modal.

## Roles

Este módulo (`FormCard`, `RecentCard`) no aplica ninguna lógica de rol propia: los dos endpoints que
consume activamente (`GET /api/clientes`, `POST /procesar`, `GET /api/documentos`) no exigen roles
específicos del lado de `services/extraccion` — consistente con
[`../extraccion_api/casos_de_uso.md`](../extraccion_api/casos_de_uso.md) "Resumen de auth por
endpoint": "este servicio no tiene roles ni RLS propios". El único punto de este módulo con
restricción de rol real es el modal huérfano, indirectamente, a través de `_ROLES_ESCRITURA` del
backend de `services/presupuestacion` (ver tabla arriba) — pero esa restricción no se ejercita hoy
porque el componente no está montado.
