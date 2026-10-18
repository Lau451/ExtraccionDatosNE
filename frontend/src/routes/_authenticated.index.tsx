import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { CargaDocumentos } from '@/features/carga-documentos/CargaDocumentos'
import { CARGA_DOCUMENTOS_ROLES } from '@/features/carga-documentos/roles'

// Los roles denegados rebotan a su propio home (homeForRol), nunca a "/".
export const Route = createFileRoute('/_authenticated/')({
  beforeLoad: requireRole(...CARGA_DOCUMENTOS_ROLES),
  component: CargaDocumentos,
})
