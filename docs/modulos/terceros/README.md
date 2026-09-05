# Módulo Terceros — `services/terceros/`

## Qué es

Terceros concentra la identidad de toda entidad externa a la droguería —hospitales,
obras sociales, laboratorios, distribuidores, etc.— que antes vivía duplicada en
`clientes` y `proveedores`. Nace del change `terceros-modelo`
(`openspec/changes/terceros-modelo/`) para resolver que una misma empresa que es a la
vez cliente y proveedor tenía dos identidades sin relación entre sí (dos nombres, dos
CUIT, sin forma de saber que eran la misma entidad).

Es un módulo de **nivel superior**, hermano de `services/presupuestacion/` y
`services/extraccion/` bajo `services/` — no un submódulo de presupuestación. Gobierna
8 tablas nuevas (migración `supabase/migrations/0008_terceros_modelo.sql`) organizadas
en 4 subdominios, cada uno con el cuarteto `models.py` / `repository.py` / `service.py`
/ `router.py`:

| Subdominio | Tablas | Raíz de agregado |
|---|---|---|
| `identidad/` | `terceros`, y los roles `clientes`/`proveedores` (tablas compartidas con `services/presupuestacion/`, angostas) | `Tercero` |
| `catalogos/` | `sectores_contacto`, `condiciones_pago`, `formas_pago` | catálogos por droguería |
| `direcciones/` | `tercero_direcciones`, `direccion_usos` | `TerceroDireccion` |
| `contactos/` | `terceros_contactos` | `TerceroContacto` |

## Qué NO hace

- **No importa nada de `services.presupuestacion`** (D5, ver [`decisiones.md`](./decisiones.md)
  D-TERCEROS-005). La dependencia es de una sola dirección:
  `presupuestacion/** → services.terceros.api → terceros/*/service.py`. Verificado por
  `tests/terceros/test_dependencias.py`, que recorre con `ast` todos los `.py` bajo
  `services/terceros/` y falla si aparece cualquier `import services.presupuestacion`.
- **No expone direcciones ni condiciones de pago al import legado por CSV.** El RPC
  `upsert_terceros_legacy` (`services/presupuestacion/imports/`, ver
  [`../terceros/decisiones.md`](./decisiones.md) D-TERCEROS-001) solo resuelve
  identidad (`razon_social`, `cuit`, `codigo_interno`) y el rol (`tipo`,
  `es_competidor`, `es_proveedor_compra`) — nunca crea `tercero_direcciones` ni asigna
  `condicion_pago_id`/`forma_pago_id`. Fuera de alcance de este change.
- **No define un endpoint `DELETE` físico para ningún sub-recurso.** Solo baja lógica
  vía `activo=false` (D4), salvo `tercero_direcciones`, donde `eliminar_direccion` sí
  es un `DELETE` físico (ver `terceros-direcciones/spec.md`, "Address Edit and
  Removal").

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `terceros/errors.py` | `asegurar_tercero_de_la_drogueria(...)` — el único guard de tenant/`superadmin` del módulo (D3). |
| `terceros/api.py` | Fachada unidireccional: reexporta modelos y funciones de servicio de los 4 subdominios. Único punto de entrada permitido para `services/presupuestacion/`. |
| `terceros/router.py` | Agrega los 4 sub-routers en un único `APIRouter`, montado una sola vez en `services/presupuestacion/main.py`. |
| `terceros/identidad/*` | `Tercero` + roles `ClienteRol`/`ProveedorRol`. |
| `terceros/catalogos/*` | `SectorContacto`, `CondicionPago`, `FormaPago`. |
| `terceros/direcciones/*` | `TerceroDireccion` + `DireccionUso` (N:M por `uso`). |
| `terceros/contactos/*` | `TerceroContacto`. |

## Quién lo consume

- `services/presupuestacion/main.py` monta `terceros_router` (Fase 7).
- `services/presupuestacion/clientes/service.py` y `services/presupuestacion/catalogo/service.py`
  resuelven identidad/roles/contactos exclusivamente vía `services.terceros.api`
  (Fase 8, D5).
- `services/presupuestacion/imports/repository.py` llama al RPC `upsert_terceros_legacy`
  directo por `client.rpc(...)` (Fase 9) — es la única excepción documentada a "pasar
  siempre por `services.terceros.api`": el RPC vive en la base, no en un módulo Python
  de `services/terceros/`, así que no hay ciclo de imports posible (D5 solo restringe
  imports de módulos Python).
- `services/extraccion/routers/clientes.py` lee `terceros.razon_social` vía embedding
  de PostgREST (`clientes(id, terceros(razon_social))`) — no pasa por `services.terceros.api`
  porque `services/extraccion/**` no está bajo la regla D5 (esa regla es específica de
  `services/presupuestacion/**`).

## Documentos del módulo

- [`decisiones.md`](./decisiones.md) — D1-D6 (design.md), citadas explícitamente.
- [`base_de_datos.md`](./base_de_datos.md) — las 8 tablas nuevas.

Para `UsuarioPerfil`, `require_roles`, `get_service_client`/`get_user_client` y las 3
excepciones compartidas (`NotFoundError`/`ForbiddenError`/`ValidationError`/`ConflictError`),
ver `services/shared/` — extraído en la Fase 2 de este mismo change para que
`services/terceros/` pudiera depender de ellos sin importar `services.presupuestacion`.
