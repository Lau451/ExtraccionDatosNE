import { createFileRoute } from '@tanstack/react-router'
import { SetPasswordForm } from '@/features/auth/SetPasswordForm'
import { useSessionFromLink } from '@/features/auth/useSessionFromLink'

export const Route = createFileRoute('/accept-invite')({
  component: AcceptInvitePage,
})

function AcceptInvitePage() {
  const { checking, hasSession } = useSessionFromLink()

  return (
    <div className="flex min-h-svh items-center justify-center bg-slate-50">
      <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-6 text-lg font-semibold text-navy">Droguería Nueva Era</h1>
        {checking ? (
          <p className="text-sm text-slate-500">Verificando invitación…</p>
        ) : hasSession ? (
          <SetPasswordForm title="Creá tu contraseña para activar tu cuenta" submitLabel="Activar cuenta" />
        ) : (
          <p className="max-w-sm text-sm text-red-600">
            Este link de invitación no es válido o ya expiró. Pedile a tu administrador que te
            reenvíe la invitación.
          </p>
        )}
      </div>
    </div>
  )
}
