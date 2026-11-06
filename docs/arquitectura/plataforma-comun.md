# Plataforma común — usuarios, permisos, datos y experiencia

Cómo comparten los módulos usuarios, permisos e información sin acoplarse, cómo
evoluciona cada uno a su ritmo y cómo se mantiene una sola experiencia para el
usuario. Los principios (P1–P10) se definen en [`README.md`](./README.md).

## Usuarios e identidad

| Tema | Decisión | Estado |
|------|----------|--------|
| Autenticación | Una sola identidad: Supabase Auth + JWT, verificado por el kernel compartido `services/shared/auth_jwt.py`. Todos los módulos y unidades desplegables usan el mismo token. | **[IMPLEMENTADO]** |
| Tenant | `drogueria_id` en cada tabla de negocio, con RLS en la base como barrera final (ver [`../reglas-globales.md`](../reglas-globales.md)). | **[IMPLEMENTADO]** |
| Perfil | Lo resuelve `plataforma` una vez por request y lo entrega a los módulos (`UsuarioPerfil`). Ningún módulo consulta la tabla de usuarios por su cuenta. | **[RECOMENDACIÓN]** |

## Permisos por capacidad (P7)

**[RECOMENDACIÓN]**

1. Cada módulo **declara sus capacidades** en un manifiesto: `pcp.leer`, `pcp.escribir`, `presupuestos.importar_legacy`, etc.
2. Un rol es un **conjunto de capacidades guardado como dato** (tabla rol → capacidades), editable sin desplegar código.
3. Los endpoints verifican capacidades con una dependencia de `plataforma` (`require_capability("pcp.escribir")`), no con tuplas de roles.
4. El frontend recibe la lista de capacidades del usuario y la usa para el menú y para mostrar u ocultar acciones. El backend siempre vuelve a verificar.

**Migración:** cada tupla actual (por ejemplo, `ROLES_ESCRITURA_PCP` en `services/pcp/roles.py:16`) se traduce a una capacidad con el mismo conjunto inicial de roles, así que no cambia el comportamiento. Se hace módulo por módulo.

## Cómo se comparte información entre módulos

De más acoplado a menos acoplado. Se usa el mecanismo más débil que resuelva el caso.

| Mecanismo | Cuándo | Ejemplo |
|-----------|--------|---------|
| **Fachada** (`api.py`) | Lecturas o comandos que necesitan respuesta en el momento | `comercial` pide un producto a `productos.api` |
| **Evento de dominio** (outbox) | Otro módulo reacciona a algo que pasó y quien lo emitió no necesita la respuesta | "OC exportada" → notificaciones, analítica, agentes |
| **Vista de lectura publicada** | Reportes y analítica que cruzan módulos | Vista de ventas por cliente y período, mantenida por su dueño |

**[RECOMENDACIÓN]** Eventos: una tabla outbox en Postgres (D-ARQ-005). El módulo emisor
escribe el evento en la misma transacción que su cambio, y un proceso lo entrega a los
suscriptores. `presupuestacion/eventos` es la semilla. Reglas:

- Los eventos se nombran en pasado y por dominio: `oc.exportada`, `presupuesto.aprobado`.
- El payload lleva ids y los datos mínimos, no la fila completa.
- Los suscriptores son idempotentes: si un evento llega dos veces, se aplica una sola vez.

## Cómo evitar duplicar datos y reglas

- **Un dueño por dato (P1).** Si otro módulo necesita un dato, lo pide; no lo copia.
- **Una regla vive en un solo lugar.** Si dos módulos necesitan la misma regla, va en el dueño del dato y se expone por su fachada. Ejemplo de lo que hay que evitar: el versionado de costos duplicado (X-ARQ-004 en [`mapa-modulos.md`](./mapa-modulos.md)).
- **Lo que viene de Progress no se reinterpreta (P4).** Se guarda tal como llegó, con origen y fecha de sincronización.
- **Copias permitidas:** solo una "foto" histórica deliberada (por ejemplo, el precio al momento de presupuestar), documentada como tal.

## Evolución a distinta velocidad

| Herramienta | Qué permite |
|-------------|-------------|
| Contrato por módulo: fachada + eventos + rutas HTTP | Mientras el contrato no cambie, el interior del módulo cambia libremente. |
| Tests de dependencias por módulo | Detectan en CI cuando un módulo empieza a acoplarse a otro. |
| Migraciones con prefijo del módulo dueño | Se sabe de quién es cada cambio de esquema. |
| Feature flags por módulo y por droguería | Un módulo nuevo se habilita de a poco. `planes` (`presupuestacion/planes`) es la semilla. |
| `docs/modulos/<modulo>/` + `contrato.md` | Cada módulo documenta qué ofrece y qué promete no romper. |

Un cambio que rompe un contrato se versiona (ruta `/v2`, evento `.v2`) y convive con
la versión anterior hasta que no quedan consumidores.

## Experiencia unificada (P9)

**[IMPLEMENTADO]** El frontend ya es una sola SPA con shell común
(`frontend/src/features/shell/Sidebar.tsx`), rutas autenticadas `_authenticated.*` y
una carpeta por dominio en `frontend/src/features/`.

**[RECOMENDACIÓN]**

- **Manifiesto por módulo en el frontend:** rutas, entradas de menú y capacidades requeridas. El shell arma el menú combinando los manifiestos con las capacidades del usuario.
- **Sistema de diseño compartido:** componentes base en `frontend/src/components/` y direcciones de diseño en `design/`. Ningún módulo define su propio estilo de tablas, formularios o errores.
- **Un solo origen HTTP:** un proxy delante de los backends (hoy puertos 8000 y 8001), para que el frontend no dependa de cuántas unidades desplegables existen.
- **Mismo formato de error en todos los módulos:** el que ya define `services/shared/exceptions.py`.
