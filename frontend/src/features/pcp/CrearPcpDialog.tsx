import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { crearPcp, listarPresupuestosElegibles } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

export function CrearPcpDialog() {
  const [open, setOpen] = useState(false)
  const [presupuestoId, setPresupuestoId] = useState('')
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos', 'elegibles-para-pcp'],
    queryFn: listarPresupuestosElegibles,
    enabled: open,
  })
  const presupuestoEsElegible = presupuestos.some(({ id }) => id === presupuestoId)
  const mutation = useMutation({
    mutationFn: () => crearPcp({ presupuesto_id: presupuestoId }),
    onSuccess: (pcp) => {
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.listas() })
      setOpen(false)
      navigate({ to: '/pcp/$pcpId', params: { pcpId: pcp.id } })
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white active:scale-[0.96]"
        >
          Nuevo PCP
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-navy">Nuevo PCP</Dialog.Title>
          <form
            className="mt-4 space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (presupuestoEsElegible) mutation.mutate()
            }}
          >
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Presupuesto elegible</span>
              <select
                required
                value={presupuestoId}
                onChange={(event) => setPresupuestoId(event.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2"
              >
                <option value="">Seleccioná un presupuesto</option>
                {presupuestos.map((presupuesto) => (
                  <option key={presupuesto.id} value={presupuesto.id}>
                    {presupuesto.nombre}
                  </option>
                ))}
              </select>
            </label>
            {mutation.isError && (
              <p role="alert" className="text-sm text-red-600">No se pudo crear el PCP.</p>
            )}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button type="button" className="min-h-10 px-3 text-sm text-slate-600">Cancelar</button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={mutation.isPending || !presupuestoEsElegible}
                className="min-h-10 rounded-md bg-navy px-3 text-sm font-medium text-white disabled:opacity-50"
              >
                {mutation.isPending ? 'Creando…' : 'Crear'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
