import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { CargaDocumentos } from '@/features/carga-documentos/CargaDocumentos'

// Los roles denegados rebotan a su propio home (homeForRol), nunca a "/".
export const Route = createFileRoute('/_authenticated/')({
  beforeLoad: requireCapacidad('extraccion.extraer'),
  component: CargaDocumentos,
})
