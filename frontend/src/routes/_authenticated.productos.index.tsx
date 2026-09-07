import { createFileRoute } from '@tanstack/react-router'
import { GestionProductos } from '@/features/productos/GestionProductos'

export const Route = createFileRoute('/_authenticated/productos/')({
  component: GestionProductos,
})
