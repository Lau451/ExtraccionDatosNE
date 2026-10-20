// Mismo formato que valida el backend (spec S1): 3-30 caracteres de
// `a-z 0-9 . _ -`, guardado en minúsculas.
const USERNAME_REGEX = /^[a-z0-9._-]{3,30}$/

export const PASSWORD_TEMPORAL_MINIMO = 8

// Same text as the backend (`usuarios/service.py` _MENSAJE_USERNAME_INVALIDO, spec S11).
export const ERROR_USERNAME =
  'El nombre de usuario debe tener entre 3 y 30 caracteres: letras, números, punto, guion o guion bajo'
export const ERROR_PASSWORD_TEMPORAL = `La contraseña temporal debe tener al menos ${PASSWORD_TEMPORAL_MINIMO} caracteres.`

export function normalizarUsername(valor: string): string {
  return valor.trim().toLowerCase()
}

export function usernameValido(username: string): boolean {
  return USERNAME_REGEX.test(username)
}

export function mensajeDeError(error: unknown, porDefecto: string): string {
  return error instanceof Error && error.message ? error.message : porDefecto
}
