import { useAuth } from './AuthContext'
import { CambiarPasswordForm } from './CambiarPasswordForm'
import { homeForRol } from './routeGuards'

/** Pantalla fuera del layout con sidebar: con el cambio forzado activo, el
 * sidebar solo llevaría a rutas que rebotan de vuelta acá. Cerrar sesión
 * queda siempre disponible para no dejar al usuario atrapado.
 *
 * `irA` es una navegación completa en la ruta real (mismo motivo que en
 * login.tsx: los guards leen auth.perfil del context del router, que recién
 * se actualiza en el próximo render). */
export function CambiarPasswordPage({ irA }: { irA: (destino: string) => void }) {
  const { perfil, signOut } = useAuth()
  const forzado = perfil?.debe_cambiar_password ?? false

  async function handleLogout() {
    await signOut()
    irA('/login')
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-2 text-lg font-semibold text-navy">Cambiar contraseña</h1>
        {forzado && (
          <p className="mb-6 text-sm text-slate-600">
            Tu contraseña es temporal. Tenés que cambiarla antes de continuar.
          </p>
        )}

        <CambiarPasswordForm onSuccess={() => irA(homeForRol(perfil?.rol))} />

        <div className="mt-6 flex justify-between border-t border-slate-200 pt-4">
          {!forzado ? (
            <button
              type="button"
              onClick={() => irA('/mi-cuenta')}
              className="text-sm text-slate-600 hover:underline"
            >
              Cancelar
            </button>
          ) : (
            <span />
          )}
          <button type="button" onClick={handleLogout} className="text-sm text-slate-600 hover:underline">
            Cerrar sesión
          </button>
        </div>
      </div>
    </div>
  )
}
