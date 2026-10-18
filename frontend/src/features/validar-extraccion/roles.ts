import type { Rol } from '@/features/auth/AuthContext'

/** Listado, detalle y validación de extracciones (spec S2): mismos roles que
 * la carga de documentos. */
export const VALIDAR_EXTRACCION_ROLES: Rol[] = ['admin', 'gerencia', 'lider_comercial', 'comercial']
