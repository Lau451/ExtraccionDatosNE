import { createFileRoute } from '@tanstack/react-router'
import { Compromisos } from '@/features/compromisos/Compromisos'

export const Route = createFileRoute('/_authenticated/compromisos')({
  component: Compromisos,
})
