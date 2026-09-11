import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  registrarResultado,
  type ProductoProveedor,
  type RegistrarResultadoPayload,
  type ResultadoNegociacionTipo,
} from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

export function RegistrarResultadoDialog({
  pcpId,
  renglonId,
  proveedor,
}: {
  pcpId: string
  renglonId: string
  proveedor: ProductoProveedor
}) {
  const [open, setOpen] = useState(false)
  const [resultado, setResultado] = useState<ResultadoNegociacionTipo>('precio_obtenido')
  const [precioUnitario, setPrecioUnitario] = useState('')
  const [cantidadMinima, setCantidadMinima] = useState('')
  const [cantidadMaxima, setCantidadMaxima] = useState('')
  const [mantenimientoHasta, setMantenimientoHasta] = useState('')
  const [condicionPagoId, setCondicionPagoId] = useState('')
  const [formaPagoId, setFormaPagoId] = useState('')
  const [motivo, setMotivo] = useState('')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => {
      const payload: RegistrarResultadoPayload = { resultado }
      if (resultado === 'precio_obtenido') {
        if (precioUnitario) payload.precio_unitario = Number(precioUnitario)
        if (cantidadMinima) payload.cantidad_minima = Number(cantidadMinima)
        if (cantidadMaxima) payload.cantidad_maxima = Number(cantidadMaxima)
        if (mantenimientoHasta) payload.mantenimiento_hasta = mantenimientoHasta
        if (condicionPagoId) payload.condicion_pago_id = condicionPagoId
        if (formaPagoId) payload.forma_pago_id = formaPagoId
      } else if (motivo) {
        payload.motivo = motivo
      }
      return registrarResultado(pcpId, renglonId, proveedor.proveedor_id, payload)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(pcpQueryKeys.resultado(pcpId, renglonId, proveedor.proveedor_id), data)
      setOpen(false)
    },
  })

  const codigo = proveedor.codigo_proveedor ?? proveedor.proveedor_id

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="min-h-9 rounded-md border border-slate-300 px-3 text-sm font-medium text-navy">
          Registrar resultado
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-navy">{`Registrar resultado — ${codigo}`}</Dialog.Title>
          <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}>
            <label className="block text-sm text-slate-600">
              Resultado
              <select
                value={resultado}
                onChange={(event) => setResultado(event.target.value as ResultadoNegociacionTipo)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
              >
                <option value="precio_obtenido">Precio obtenido</option>
                <option value="no_cotiza">No cotiza</option>
              </select>
            </label>
            {resultado === 'precio_obtenido' ? (
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm text-slate-600">
                  Precio unitario
                  <input
                    type="number"
                    value={precioUnitario}
                    onChange={(event) => setPrecioUnitario(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  Cantidad mínima
                  <input
                    type="number"
                    value={cantidadMinima}
                    onChange={(event) => setCantidadMinima(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  Cantidad máxima
                  <input
                    type="number"
                    value={cantidadMaxima}
                    onChange={(event) => setCantidadMaxima(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  Mantenimiento hasta
                  <input
                    type="date"
                    value={mantenimientoHasta}
                    onChange={(event) => setMantenimientoHasta(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  Condición de pago
                  <input
                    type="text"
                    value={condicionPagoId}
                    onChange={(event) => setCondicionPagoId(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  Forma de pago
                  <input
                    type="text"
                    value={formaPagoId}
                    onChange={(event) => setFormaPagoId(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                  />
                </label>
              </div>
            ) : (
              <label className="block text-sm text-slate-600">
                Motivo
                <input
                  type="text"
                  value={motivo}
                  onChange={(event) => setMotivo(event.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                />
              </label>
            )}
            {mutation.isError ? (
              <p role="alert" className="text-sm text-red-600">
                {mutation.error instanceof Error ? mutation.error.message : 'No se pudo registrar el resultado.'}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild><button type="button" className="min-h-10 px-3 text-sm text-slate-600">Cancelar</button></Dialog.Close>
              <button type="submit" disabled={mutation.isPending} className="min-h-10 rounded-md bg-navy px-3 text-sm font-medium text-white disabled:opacity-50">
                {mutation.isPending ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
