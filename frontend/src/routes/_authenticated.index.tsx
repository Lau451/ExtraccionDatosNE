import { createFileRoute } from '@tanstack/react-router'
import { CargaDocumentos } from '@/features/carga-documentos/CargaDocumentos'

export const Route = createFileRoute('/_authenticated/')({
  component: CargaDocumentos,
})
