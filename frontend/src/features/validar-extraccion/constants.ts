// D7 -- mismo valor que services/presupuestacion/extraccion/models.py:MAX_FILAS_EDITABLES.
// Duplicación deliberada (no hay codegen en el repo): cada lado documenta el otro.
// Frontend: gate duro antes de pedir /filas (no se edita, se ofrece "confirmar tal cual").
// Backend: chequeo defensivo sobre el payload editado (`_validar_filas_override`).
export const MAX_FILAS_EDITABLES = 500
