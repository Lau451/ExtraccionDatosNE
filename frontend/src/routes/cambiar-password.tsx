import { createFileRoute } from '@tanstack/react-router'
import { CambiarPasswordPage } from '@/features/auth/CambiarPasswordPage'
import { requireSession } from '@/features/auth/routeGuards'

// requireSession y no requireAuth: esta ruta es justamente el destino del
// cambio forzado (spec S3) — con requireAuth se redirigiría a sí misma.
export const Route = createFileRoute('/cambiar-password')({
  beforeLoad: requireSession,
  component: () => <CambiarPasswordPage irA={irA} />,
})

// Navegación completa a propósito, ver irA() en login.tsx.
function irA(destino: string) {
  window.location.href = destino
}
