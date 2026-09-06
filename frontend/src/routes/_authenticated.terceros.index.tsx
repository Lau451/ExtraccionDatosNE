import { createFileRoute } from '@tanstack/react-router'
import { GestionTerceros } from '@/features/terceros/GestionTerceros'

export const Route = createFileRoute('/_authenticated/terceros/')({
  component: GestionTerceros,
})
