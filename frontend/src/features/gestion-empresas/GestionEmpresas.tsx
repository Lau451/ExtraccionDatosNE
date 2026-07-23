import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { actualizarDrogueria, eliminarDrogueria, listarDroguerias, type Drogueria } from '@/lib/api/droguerias'
import { listarPlanes } from '@/lib/api/planes'
import { CrearDrogueriaDialog } from './CrearDrogueriaDialog'
import { CrearPrimerAdminDialog } from './CrearPrimerAdminDialog'

export function GestionEmpresas() {
  const queryClient = useQueryClient()
  const [aEliminar, setAEliminar] = useState<Drogueria | null>(null)
  const { data: droguerias, isPending } = useQuery({
    queryKey: ['droguerias'],
    queryFn: listarDroguerias,
  })
  const { data: planes } = useQuery({ queryKey: ['planes'], queryFn: listarPlanes })

  const actualizarMutation = useMutation({
    mutationFn: ({ id, ...payload }: { id: string; activa?: boolean; plan_id?: string | null }) =>
      actualizarDrogueria(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['droguerias'] }),
  })

  const eliminarMutation = useMutation({
    mutationFn: (id: string) => eliminarDrogueria(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['droguerias'] })
      setAEliminar(null)
    },
  })

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-navy">Empresas</h1>
        <CrearDrogueriaDialog />
      </div>

      {(actualizarMutation.isError || eliminarMutation.isError) && (
        <p className="mb-4 text-sm text-red-600">
          {eliminarMutation.error instanceof Error
            ? eliminarMutation.error.message
            : 'No se pudo aplicar el cambio.'}
        </p>
      )}

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Nombre</th>
              <th className="py-2 font-medium">CUIT</th>
              <th className="py-2 font-medium">Plan</th>
              <th className="py-2 font-medium">Estado</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {droguerias?.map((drogueria) => (
              <FilaDrogueria
                key={drogueria.id}
                drogueria={drogueria}
                planes={planes ?? []}
                onCambiarPlan={(plan_id) => actualizarMutation.mutate({ id: drogueria.id, plan_id })}
                onCambiarActiva={(activa) => actualizarMutation.mutate({ id: drogueria.id, activa })}
                onEliminar={() => setAEliminar(drogueria)}
              />
            ))}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={aEliminar !== null}
        onOpenChange={(open) => !open && setAEliminar(null)}
        title="Eliminar empresa"
        description={`¿Eliminar la empresa "${aEliminar?.nombre ?? ''}"? Esta acción no se puede deshacer.`}
        isPending={eliminarMutation.isPending}
        onConfirm={() => aEliminar && eliminarMutation.mutate(aEliminar.id)}
      />
    </div>
  )
}

function FilaDrogueria({
  drogueria,
  planes,
  onCambiarPlan,
  onCambiarActiva,
  onEliminar,
}: {
  drogueria: Drogueria
  planes: { id: string; nombre: string }[]
  onCambiarPlan: (planId: string | null) => void
  onCambiarActiva: (activa: boolean) => void
  onEliminar: () => void
}) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2">{drogueria.nombre}</td>
      <td className="py-2 text-slate-500">{drogueria.cuit}</td>
      <td className="py-2">
        <select
          value={drogueria.plan_id ?? ''}
          onChange={(event) => onCambiarPlan(event.target.value || null)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="">Sin plan</option>
          {planes.map((plan) => (
            <option key={plan.id} value={plan.id}>
              {plan.nombre}
            </option>
          ))}
        </select>
      </td>
      <td className="py-2">
        <span className={drogueria.activa ? 'text-emerald-600' : 'text-slate-400'}>
          {drogueria.activa ? 'Activa' : 'Suspendida'}
        </span>
      </td>
      <td className="py-2 text-right space-x-3">
        <CrearPrimerAdminDialog drogueriaId={drogueria.id} drogueriaNombre={drogueria.nombre} />
        <button
          type="button"
          onClick={() => onCambiarActiva(!drogueria.activa)}
          className="text-sm font-medium text-accent hover:underline"
        >
          {drogueria.activa ? 'Suspender' : 'Reactivar'}
        </button>
        <button
          type="button"
          onClick={onEliminar}
          className="text-sm font-medium text-red-600 hover:underline"
        >
          Eliminar
        </button>
      </td>
    </tr>
  )
}
