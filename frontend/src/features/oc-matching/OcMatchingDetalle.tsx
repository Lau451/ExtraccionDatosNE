import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  confirmarVinculo,
  deshacerVinculo,
  descartarRenglon,
  obtenerMatching,
  obtenerPresupuestosCandidatos,
  type MatchingOut,
} from '@/lib/api/ocMatching'
import { ColumnaOrdenCompra } from './components/ColumnaOrdenCompra'
import { ColumnaPresupuesto } from './components/ColumnaPresupuesto'
import { SelectorPresupuesto } from './components/SelectorPresupuesto'

function fechaLegible(iso: string): string {
  const fecha = new Date(iso)
  return Number.isNaN(fecha.getTime()) ? iso : fecha.toLocaleString('es-AR')
}

/** Mutación diferida hasta que el usuario confirme el aviso de OC exportada. */
type AccionPendiente =
  | { tipo: 'confirmar'; ocItemId: string; presupuestoItemId: string }
  | { tipo: 'deshacer'; ocItemId: string }
  | { tipo: 'descartar'; ocItemId: string }

interface Props {
  ordenCompraId: string
  /** Presupuesto elegido en esta sesión, leído del search param de la ruta
   * (design.md D8). `undefined` cuando todavía no se eligió -- el servidor lo
   * resuelve (vínculos confirmados > query param > sugerido del ranking). */
  presupuestoId?: string
}

/** Container de la pantalla de matching (design.md § Forma del frontend, D12,
 * D13): 2 queries (`presupuestos-candidatos`, `matching`), 3 mutaciones
 * (confirmar/deshacer/descartar). El único estado local es el renglón de OC
 * resaltado -- el presupuesto elegido NO es estado local (D8, alternativa
 * (b) rechazada): vive en la URL, y este componente lo sincroniza navegando.
 * Cada mutación reemplaza la cache con el `MatchingOut` completo que devuelve
 * (D13): sin refetch por click. */
export function OcMatchingDetalle({ ordenCompraId, presupuestoId }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [renglonSeleccionadoId, setRenglonSeleccionadoId] = useState<string | null>(null)
  const [accionPendiente, setAccionPendiente] = useState<AccionPendiente | null>(null)

  const candidatosQuery = useQuery({
    queryKey: ['oc-matching', ordenCompraId, 'presupuestos-candidatos'],
    queryFn: () => obtenerPresupuestosCandidatos(ordenCompraId),
  })

  const matchingQueryKey = ['oc-matching', ordenCompraId, 'matching', presupuestoId ?? null] as const
  const matchingQuery = useQuery({
    queryKey: matchingQueryKey,
    queryFn: () => obtenerMatching(ordenCompraId, presupuestoId),
  })

  function reemplazarCache(resultado: MatchingOut) {
    queryClient.setQueryData(matchingQueryKey, resultado)
  }

  // Mapa presupuesto_item_id -> RenglonPresupuesto (design.md D13): resuelve
  // la etiqueta de cada candidato en `RenglonOcFila` sin volver a pedirle nada
  // al servidor. Se calcula antes de los `return` tempranos de abajo para no
  // romper el orden de hooks.
  const presupuestoPorId = useMemo(() => {
    const renglones = matchingQuery.data?.renglones_presupuesto ?? []
    return new Map(renglones.map((renglon) => [renglon.presupuesto_item_id, renglon]))
  }, [matchingQuery.data])

  const confirmarMutation = useMutation({
    mutationFn: ({ ocItemId, presupuestoItemId }: { ocItemId: string; presupuestoItemId: string }) =>
      confirmarVinculo(ordenCompraId, ocItemId, presupuestoItemId),
    onSuccess: reemplazarCache,
  })

  const deshacerMutation = useMutation({
    mutationFn: (ocItemId: string) => deshacerVinculo(ordenCompraId, ocItemId),
    onSuccess: reemplazarCache,
  })

  const descartarMutation = useMutation({
    mutationFn: (ocItemId: string) => descartarRenglon(ordenCompraId, ocItemId),
    onSuccess: reemplazarCache,
  })

  const isPending =
    confirmarMutation.isPending || deshacerMutation.isPending || descartarMutation.isPending

  // Compartido entre el radio de candidatos (columna derecha) y el vínculo
  // manual a cualquier renglón del presupuesto (columna izquierda, T4): ambos
  // terminan en el mismo POST /vinculo -- el backend decide `vinculo_origen`
  // según si el precio coincide o no.
  function confirmarVinculoDe(ocItemId: string, presupuestoItemId: string) {
    solicitar({ tipo: 'confirmar', ocItemId, presupuestoItemId })
  }

  function ejecutar(accion: AccionPendiente, opciones?: { onSuccess: () => void }) {
    if (accion.tipo === 'confirmar') {
      confirmarMutation.mutate(
        { ocItemId: accion.ocItemId, presupuestoItemId: accion.presupuestoItemId },
        opciones,
      )
    } else if (accion.tipo === 'deshacer') {
      deshacerMutation.mutate(accion.ocItemId, opciones)
    } else {
      descartarMutation.mutate(accion.ocItemId, opciones)
    }
  }

  // Si la OC ya se exportó a Progress se edita igual, pero antes se avisa que
  // el cambio no llega a Progress: la acción espera en `accionPendiente`.
  function solicitar(accion: AccionPendiente) {
    if (matchingQuery.data?.exportacion) {
      // Sin esto el diálogo mostraría el error de un intento anterior fallido.
      confirmarMutation.reset()
      deshacerMutation.reset()
      descartarMutation.reset()
      setAccionPendiente(accion)
    } else ejecutar(accion)
  }

  const mutacionPendiente =
    accionPendiente?.tipo === 'confirmar'
      ? confirmarMutation
      : accionPendiente?.tipo === 'deshacer'
        ? deshacerMutation
        : descartarMutation

  function elegirPresupuesto(id: string) {
    navigate({
      to: '/ordenes-compra/$ordenCompraId/matching',
      params: { ordenCompraId },
      search: (previo: Record<string, unknown>) => ({ ...previo, presupuesto: id }),
      replace: true,
    })
  }

  if (matchingQuery.isPending) {
    return <div className="px-6 py-10 text-sm text-slate-500">Cargando matching…</div>
  }

  if (matchingQuery.isError || !matchingQuery.data) {
    return (
      <div className="px-6 py-10 text-sm text-red-600">
        {matchingQuery.error instanceof Error
          ? matchingQuery.error.message
          : 'No se pudo cargar el matching de esta orden de compra.'}
      </div>
    )
  }

  const matching = matchingQuery.data
  const renglonSeleccionado =
    matching.renglones_oc.find((renglon) => renglon.oc_item_id === renglonSeleccionadoId) ?? null

  // Gate de planificación (T4, odd/tasks/oc-entregas-planificacion.md): el
  // backend rechaza planificar con 409 mientras haya renglones `pendiente`
  // (oc_entregas/service.py::planificar_entregas) -- esta pantalla ya tiene
  // ese dato, así que el botón se deshabilita acá mismo en vez de dejar que
  // el usuario llegue a la otra pantalla para enterarse recién ahí.
  const hayRenglonesPendientes = matching.renglones_oc.some((renglon) => renglon.estado === 'pendiente')

  function irAPlanificarEntregas() {
    navigate({ to: '/ordenes-compra/$ordenCompraId/entregas', params: { ordenCompraId } })
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-10">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-xl font-semibold text-slate-900">
            Matching de orden de compra {matching.numero_oc}
          </h1>
          <button
            type="button"
            disabled={hayRenglonesPendientes}
            title={
              hayRenglonesPendientes
                ? 'Resolvé los renglones pendientes antes de planificar las entregas'
                : undefined
            }
            onClick={irAPlanificarEntregas}
            className="shrink-0 rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Planificar entregas
          </button>
        </div>
        {matching.exportacion && (
          <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            Esta orden de compra ya fue exportada a Progress el {fechaLegible(matching.exportacion.exportado_at)}
            {matching.exportacion.exportado_por_nombre ? ` por ${matching.exportacion.exportado_por_nombre}` : ''}.
            Los cambios de matching que hagas no se envían a Progress.
          </p>
        )}
        {matching.advertencias.map((advertencia) => (
          <p key={advertencia} className="text-sm text-amber-600">
            {advertencia}
          </p>
        ))}
      </header>

      {candidatosQuery.data && (
        <SelectorPresupuesto
          data={candidatosQuery.data}
          presupuestoIdSeleccionado={matching.presupuesto_id}
          onSeleccionar={elegirPresupuesto}
        />
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <ColumnaPresupuesto
          renglones={matching.renglones_presupuesto}
          renglonOcSeleccionado={renglonSeleccionado}
          isPending={isPending}
          onVincularManual={confirmarVinculoDe}
        />
        <ColumnaOrdenCompra
          renglones={matching.renglones_oc}
          renglonSeleccionadoId={renglonSeleccionadoId}
          isPending={isPending}
          presupuestoPorId={presupuestoPorId}
          onSeleccionar={setRenglonSeleccionadoId}
          onConfirmar={(ocItemId, presupuestoItemId) =>
            confirmarVinculoDe(ocItemId, presupuestoItemId)
          }
          onDeshacer={(ocItemId) => solicitar({ tipo: 'deshacer', ocItemId })}
          onDescartar={(ocItemId) => solicitar({ tipo: 'descartar', ocItemId })}
        />
      </div>

      <ConfirmDialog
        open={accionPendiente !== null}
        onOpenChange={(abierto) => {
          if (!abierto) setAccionPendiente(null)
        }}
        title="Orden de compra ya exportada"
        description="Esta orden de compra ya fue exportada a Progress. El cambio de matching se guardará acá, pero no se enviará a Progress."
        confirmLabel="Modificar igual"
        pendingLabel="Modificando…"
        isPending={mutacionPendiente.isPending}
        error={mutacionPendiente.error instanceof Error ? mutacionPendiente.error.message : null}
        onConfirm={() => {
          // Se cierra recién al terminar bien: si falla, el error se ve en el diálogo.
          if (accionPendiente) ejecutar(accionPendiente, { onSuccess: () => setAccionPendiente(null) })
        }}
      />
    </div>
  )
}
