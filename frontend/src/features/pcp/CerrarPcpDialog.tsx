import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { cerrarPcp, type Pcp } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

export function CerrarPcpDialog({ pcpId }: { pcpId: string }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => cerrarPcp(pcpId),
    onSuccess: (actualizado) => {
      queryClient.setQueryData(pcpQueryKeys.detalle(pcpId), actualizado)
      queryClient.setQueriesData<Pcp[]>({ queryKey: pcpQueryKeys.listas() }, (pcps) =>
        Array.isArray(pcps) ? pcps.map((pcp) => (pcp.id === pcpId ? actualizado : pcp)) : pcps,
      )
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.renglones(pcpId), refetchType: 'none' })
      queryClient.invalidateQueries({ queryKey: ['pcp', 'sugerencias'] })
      setOpen(false)
    },
  })

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-10 rounded-md bg-red-700 px-3 text-sm font-medium text-white active:scale-[0.96]"
      >
        Cerrar PCP
      </button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Cerrar PCP"
        description="Esta acción finaliza el PCP y sus recursos relacionados."
        onConfirm={() => mutation.mutate()}
        confirmLabel="Confirmar cierre"
        pendingLabel="Cerrando…"
        isPending={mutation.isPending}
        error={mutation.isError ? 'No se pudo cerrar el PCP.' : null}
      />
    </>
  )
}
