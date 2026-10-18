import type { Rol } from '@/features/auth/AuthContext'

/** Carga de documentos y extracción con IA (spec S1). `compras` no participa
 * por ahora de ningún proceso de extracción y `superadmin` no la ve. Espejo
 * del guard de `services/extraccion`. */
export const CARGA_DOCUMENTOS_ROLES: Rol[] = ['admin', 'gerencia', 'lider_comercial', 'comercial']
