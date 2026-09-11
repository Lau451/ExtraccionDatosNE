import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listarResultadosRenglon, seleccionarProveedores, type ProductoProveedor } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

export function SeleccionProveedoresSection({
  pcpId,
  renglonId,
  proveedores,
  puedeEscribir,
}: {
  pcpId: string
  renglonId: string
  proveedores: ProductoProveedor[]
  puedeEscribir: boolean
}) {
  const [proveedorIds, setProveedorIds] = useState<string[]>([])
  const queryClient = useQueryClient()

  // Misma clave que usa ComparacionProveedoresTable -- React Query dedupe el
  // fetch (un solo round trip real) -- para saber qué proveedores ya tienen
  // un resultado de negociación registrado. Reofrecerlos acá y volver a
  // enviarlos en el batch de seleccionarProveedores dispara un 23505 (UNIQUE
  // pcp_renglon_id+proveedor_id) que hace fallar el insert entero, incluidos
  // los proveedores realmente nuevos del mismo envío.
  const resultadosQuery = useQuery({
    queryKey: pcpQueryKeys.resultadosRenglon(pcpId, renglonId),
    queryFn: () => listarResultadosRenglon(pcpId, renglonId),
    enabled: proveedores.length > 0,
  })
  const yaConfirmados = new Set((resultadosQuery.data ?? []).map((resultado) => resultado.proveedor_id))
  const proveedoresSeleccionables = proveedores.filter((proveedor) => !yaConfirmados.has(proveedor.proveedor_id))

  const mutation = useMutation({
    mutationFn: () => seleccionarProveedores(pcpId, renglonId, proveedorIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.renglon(pcpId, renglonId), exact: true })
      // exact:true arriba deliberadamente NO cascadea a descendientes (ver
      // "Corrective Rerun — Exact renglón invalidation" en
      // apply-progress.md) -- pero eso incluía sin querer a
      // resultadosRenglon(...), que ComparacionProveedoresTable sí necesita
      // refrescar acá: nuevos proveedores confirmados quedan con "Sin
      // resultado aún" hasta que su fila (sin_respuesta) exista y se lea.
      // Se invalida explícitamente en vez de confiar en un prefix-match
      // implícito de renglon(...).
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.resultadosRenglon(pcpId, renglonId) })
      setProveedorIds([])
    },
  })

  function alternarProveedor(proveedorId: string, seleccionado: boolean) {
    setProveedorIds((ids) => seleccionado ? [...ids, proveedorId] : ids.filter((id) => id !== proveedorId))
  }

  return (
    <section className="mt-8" aria-labelledby="proveedores-title">
      <h2 id="proveedores-title" className="text-base font-semibold text-navy">Proveedores catalogados</h2>
      {proveedores.length === 0 ? <p className="mt-3 text-sm text-slate-500">No hay proveedores catalogados para este producto.</p> : (
        <ul aria-label="Proveedores catalogados" className="mt-3 divide-y divide-slate-100 rounded-lg bg-white shadow-sm">
          {proveedores.map((proveedor) => {
            const etiqueta = proveedor.codigo_proveedor ?? proveedor.proveedor_id
            const confirmado = yaConfirmados.has(proveedor.proveedor_id)
            return (
              <li key={proveedor.id} className="p-3 text-sm text-navy">
                {puedeEscribir && !confirmado ? (
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      aria-label={etiqueta}
                      checked={proveedorIds.includes(proveedor.proveedor_id)}
                      disabled={mutation.isPending}
                      onChange={(event) => alternarProveedor(proveedor.proveedor_id, event.target.checked)}
                    />
                    {etiqueta}
                  </label>
                ) : (
                  <span className={confirmado ? 'text-slate-500' : undefined}>
                    {etiqueta}
                    {confirmado ? ' (ya confirmado)' : null}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {puedeEscribir && proveedoresSeleccionables.length > 0 ? (
        <div className="mt-4">
          {mutation.isError ? <p role="alert" className="mb-3 text-sm text-red-600">{mutation.error instanceof Error ? mutation.error.message : 'No se pudieron confirmar los proveedores.'}</p> : null}
          <button
            type="button"
            disabled={proveedorIds.length === 0 || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            {mutation.isPending ? 'Confirmando…' : 'Confirmar proveedores'}
          </button>
        </div>
      ) : null}
    </section>
  )
}
