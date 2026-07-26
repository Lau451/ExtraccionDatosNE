import { createFileRoute } from '@tanstack/react-router'
import { ValidarExtraccionListado } from '@/features/validar-extraccion/ValidarExtraccionListado'

export const Route = createFileRoute('/_authenticated/validar-extraccion/')({
  component: ValidarExtraccionListado,
})
