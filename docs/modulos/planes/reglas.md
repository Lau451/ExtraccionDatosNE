# Reglas — Planes

Regla verificada contra el código real (`router.py`) en esta sesión. No hay tests en
`tests/planes/` — no existe ese directorio (confirmado con Glob en esta sesión), por lo
que esta regla está verificada solo por lectura de código, sin cobertura automatizada.

### RN-PLANES-001 — `GET /planes` solo devuelve planes activos

- **Descripción**: el catálogo público filtra explícitamente por `activo=True`; un
  plan desactivado deja de ser visible por esta API para cualquier rol.
- **Condición**: `.eq("activo", True)`.
- **Resultado**: la lista devuelta excluye cualquier fila con `activo=false`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/planes/router.py:18`.
- **Observaciones**: [IMPLEMENTADO]. Sin test automatizado que lo verifique (no existe
  `tests/planes/`) — pendiente si se considera necesario dado que hoy no hay forma de
  crear o desactivar un plan desde la API (ver [`decisiones.md`](./decisiones.md)), solo
  por SQL directo.

No hay ninguna otra regla de negocio en este módulo: no hay validación de tenant (la
tabla no tiene `drogueria_id`), no hay reglas de escritura (no hay escritura), y el
único rol requerido para leer es "estar autenticado" (`get_current_user`, sin
`require_roles`) — el resto de la autorización de lectura la resuelve la policy RLS
`planes_sel`, que es idéntica en condición a lo que ya exige `get_current_user` (ambas
solo piden estar autenticado), por lo que en la práctica no acota nada adicional.
