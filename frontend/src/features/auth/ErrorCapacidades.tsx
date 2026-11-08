/** Pantalla que reemplaza a la app cuando GET /auth/capacidades falló por algo
 * distinto del 403 de la contraseña temporal: sin capacidades, los guards
 * rebotan todas las rutas, así que mostrar la app vacía solo confunde. */
export function ErrorCapacidades({ mensaje, onReintentar }: { mensaje: string; onReintentar: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
      <p role="alert" className="max-w-md text-center text-sm text-red-700">
        {mensaje}
      </p>
      <button
        type="button"
        onClick={onReintentar}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        Reintentar
      </button>
    </div>
  )
}
