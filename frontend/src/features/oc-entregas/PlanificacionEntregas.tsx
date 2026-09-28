import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  obtenerPlanificacionEntregas,
  planificarEntregas,
  type EntregaPlanIn,
  type EntregaPlanOut,
  type PlanificacionEntregasOut,
  type PlanificarEntregasOut,
  type RenglonPlanificacion,
} from '@/lib/api/ocEntregas'
import { etiquetaRenglonOc } from '../oc-matching/etiquetaRenglonOc'
import { sugerirCantidadDivisible, sugerirPlanRenglon } from './sugerirPlan'

const MAX_ENTREGAS = 24

interface Props {
  ordenCompraId: string
}

/** Container de la pantalla de planificación de entregas (T4, continuación de
 * OC matching -- ver odd/tasks/oc-entregas-planificacion.md). Una sola query
 * (T3 `GET .../entregas/planificacion`) y una mutación (`PUT` del mismo
 * path). Igual que `OcMatchingDetalle` (design.md D12/D13): "nada se escribe
 * sin un click" -- el GET nunca planifica nada, solo sugiere. */
function queryKeyPlanificacion(ordenCompraId: string) {
  return ['oc-entregas', ordenCompraId, 'planificacion'] as const
}

export function PlanificacionEntregas({ ordenCompraId }: Props) {
  const query = useQuery({
    queryKey: queryKeyPlanificacion(ordenCompraId),
    queryFn: () => obtenerPlanificacionEntregas(ordenCompraId),
  })

  if (query.isPending) {
    return <div className="px-6 py-10 text-sm text-slate-500">Cargando planificación de entregas…</div>
  }

  if (query.isError || !query.data) {
    return (
      <div className="px-6 py-10 text-sm text-red-600">
        {query.error instanceof Error
          ? query.error.message
          : 'No se pudo cargar la planificación de entregas de esta orden de compra.'}
      </div>
    )
  }

  return <PlanificacionEntregasForm ordenCompraId={ordenCompraId} data={query.data} />
}

function clamp(n: number): number {
  return Math.min(MAX_ENTREGAS, Math.max(1, Math.trunc(n) || 1))
}

function nInicial(data: PlanificacionEntregasOut): number {
  const n = data.plan_actual.length > 0 ? data.plan_actual.length : data.cantidad_entregas_sugerida
  return clamp(n)
}

function cantidadEnEntrega(entrega: EntregaPlanOut, ocItemId: string): number {
  return entrega.items.find((item) => item.oc_item_id === ocItemId)?.cantidad_planificada ?? 0
}

function cantidadesIniciales(data: PlanificacionEntregasOut, n: number): Record<string, number[]> {
  if (data.plan_actual.length > 0) {
    const mapa: Record<string, number[]> = {}
    data.renglones.forEach((renglon) => {
      mapa[renglon.oc_item_id] = data.plan_actual.map((entrega) =>
        cantidadEnEntrega(entrega, renglon.oc_item_id),
      )
    })
    return mapa
  }
  const mapa: Record<string, number[]> = {}
  data.plan_sugerido.forEach((plan) => {
    mapa[plan.oc_item_id] = plan.cantidades.slice(0, n)
  })
  return mapa
}

function fechasIniciales(data: PlanificacionEntregasOut, n: number): (string | null)[] {
  if (data.plan_actual.length > 0) {
    return data.plan_actual.map((entrega) => entrega.fecha_entrega_planificada)
  }
  return Array.from({ length: n }, () => null)
}

function volverAMatching(navigate: ReturnType<typeof useNavigate>, ordenCompraId: string) {
  navigate({ to: '/ordenes-compra/$ordenCompraId/matching', params: { ordenCompraId } })
}

interface FormProps {
  ordenCompraId: string
  data: PlanificacionEntregasOut
}

function PlanificacionEntregasForm({ ordenCompraId, data }: FormProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // D4: una entrega que dejó de estar 'pendiente' bloquea la replanificación
  // (mismo criterio que el backend, service.py::planificar_entregas) -- se
  // deriva acá de los datos, no del texto de `motivo`, para no depender de un
  // string.
  const bloqueadoPorEstado = data.plan_actual.some((entrega) => entrega.estado !== 'pendiente')

  const [n, setN] = useState(() => nInicial(data))
  const [cantidades, setCantidades] = useState<Record<string, number[]>>(() =>
    cantidadesIniciales(data, nInicial(data)),
  )
  const [fechas, setFechas] = useState<(string | null)[]>(() => fechasIniciales(data, nInicial(data)))
  const [resultado, setResultado] = useState<PlanificarEntregasOut | null>(null)

  const mutation = useMutation({
    mutationFn: (entregas: EntregaPlanIn[]) => planificarEntregas(ordenCompraId, entregas),
    onSuccess: (respuesta) => {
      setResultado(respuesta)
      // Fix de review: el plan que acaba de guardarse (plan_actual, estados de
      // entrega) quedó desactualizado en la cache de la query GET -- se
      // invalida para que la próxima vez que se monte esta pantalla (o
      // cualquier otro observer activo) traiga el plan real. OcMatchingDetalle
      // no muestra estado de esta planificación (solo `renglones_oc.estado`,
      // que no cambia acá), así que no hace falta invalidar su query.
      queryClient.invalidateQueries({ queryKey: queryKeyPlanificacion(ordenCompraId) })
    },
  })

  function cambiarN(valorCrudo: number) {
    const nuevoN = clamp(valorCrudo)
    setN(nuevoN)
    setCantidades(
      Object.fromEntries(
        data.renglones.map((renglon) => [
          renglon.oc_item_id,
          sugerirPlanRenglon(renglon.cantidad, renglon.unidades_por_presentacion, nuevoN),
        ]),
      ),
    )
    setFechas((previo) => Array.from({ length: nuevoN }, (_, indice) => previo[indice] ?? null))
    setResultado(null)
  }

  function cambiarCantidad(ocItemId: string, indice: number, valor: number) {
    setCantidades((previo) => {
      const fila = [...(previo[ocItemId] ?? [])]
      fila[indice] = Number.isFinite(valor) ? valor : 0
      return { ...previo, [ocItemId]: fila }
    })
    setResultado(null)
  }

  function usarSugerida(ocItemId: string, indice: number, u: number) {
    const actual = cantidades[ocItemId]?.[indice] ?? 0
    cambiarCantidad(ocItemId, indice, sugerirCantidadDivisible(actual, u))
  }

  function cambiarFecha(indice: number, valor: string) {
    setFechas((previo) => {
      const copia = [...previo]
      copia[indice] = valor || null
      return copia
    })
  }

  const restantesPorRenglon = useMemo(() => {
    const mapa = new Map<string, number>()
    data.renglones.forEach((renglon) => {
      const suma = (cantidades[renglon.oc_item_id] ?? []).reduce((acumulado, valor) => acumulado + valor, 0)
      // Fix de review: NUMERIC(12,2) en la base -- comparar la resta cruda
      // puede dejar residuo binario (p.ej. 0.3 - (0.1 + 0.2) !== 0 por punto
      // flotante) y bloquear Guardar con una suma que en realidad coincide.
      // Redondeo a centavos, mismo criterio que
      // useFilasEditables.ts::hayDescuadre.
      mapa.set(renglon.oc_item_id, Math.round((renglon.cantidad - suma) * 100) / 100)
    })
    return mapa
  }, [data.renglones, cantidades])

  const hayDiferencias = [...restantesPorRenglon.values()].some((restante) => restante !== 0)

  // Fix de review: cuando N supera la cantidad de packs disponibles,
  // sugerirPlanRenglon (T3/D8) puede dejar una entrega entera en 0 para todos
  // los renglones -- el backend la rechaza con 422 ("no puede tener todas las
  // cantidades en cero", oc_entregas/service.py::_validar_renglones_y_cantidades).
  // Se detecta y bloquea acá antes de mandarla.
  const entregasVacias = useMemo(
    () =>
      Array.from({ length: n }, (_, indice) =>
        data.renglones.every((renglon) => (cantidades[renglon.oc_item_id]?.[indice] ?? 0) === 0),
      ),
    [data.renglones, cantidades, n],
  )
  const hayEntregaVacia = entregasVacias.some(Boolean)

  function guardar() {
    const entregas: EntregaPlanIn[] = Array.from({ length: n }, (_, indice) => ({
      numero_entrega: indice + 1,
      fecha_entrega_planificada: fechas[indice] ?? null,
      items: data.renglones.map((renglon) => ({
        oc_item_id: renglon.oc_item_id,
        cantidad: cantidades[renglon.oc_item_id]?.[indice] ?? 0,
      })),
    }))
    mutation.mutate(entregas)
  }

  if (bloqueadoPorEstado) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-10">
        <Encabezado numeroOc={data.numero_oc} descartados={data.descartados} />
        <p className="text-sm text-amber-700">{data.motivo}</p>
        <PlanBloqueadoTabla renglones={data.renglones} planActual={data.plan_actual} />
        <button
          type="button"
          onClick={() => volverAMatching(navigate, ordenCompraId)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
        >
          Volver al matching
        </button>
      </div>
    )
  }

  if (!data.puede_planificar) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-6 py-10">
        <Encabezado numeroOc={data.numero_oc} descartados={data.descartados} />
        <p className="text-sm text-amber-700">{data.motivo}</p>
        <button
          type="button"
          onClick={() => volverAMatching(navigate, ordenCompraId)}
          className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white"
        >
          Volver al matching
        </button>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-10">
      <Encabezado numeroOc={data.numero_oc} descartados={data.descartados} />

      <div>
        <label htmlFor="cantidad-entregas" className="mb-1 block text-sm text-slate-600">
          Cantidad de entregas
        </label>
        <input
          id="cantidad-entregas"
          aria-label="cantidad de entregas"
          type="number"
          min={1}
          max={MAX_ENTREGAS}
          value={n}
          onChange={(evento) => cambiarN(Number(evento.target.value))}
          className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr>
              <th className="p-2 text-left">Renglón</th>
              {Array.from({ length: n }, (_, indice) => (
                <th key={indice} className="p-2 text-left">
                  <p>Entrega {indice + 1}</p>
                  <input
                    type="date"
                    aria-label={`fecha entrega ${indice + 1}`}
                    value={fechas[indice] ?? ''}
                    onChange={(evento) => cambiarFecha(indice, evento.target.value)}
                    className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-xs"
                  />
                </th>
              ))}
              <th className="p-2 text-left">Restante</th>
            </tr>
          </thead>
          <tbody>
            {data.renglones.map((renglon) => (
              <FilaPlanificacion
                key={renglon.oc_item_id}
                renglon={renglon}
                n={n}
                valores={cantidades[renglon.oc_item_id] ?? []}
                restante={restantesPorRenglon.get(renglon.oc_item_id) ?? 0}
                onCambiar={(indice, valor) => cambiarCantidad(renglon.oc_item_id, indice, valor)}
                onUsarSugerida={(indice, u) => usarSugerida(renglon.oc_item_id, indice, u)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {entregasVacias.map(
        (vacia, indice) =>
          vacia && (
            <p key={indice} className="text-sm text-red-600">
              La entrega {indice + 1} no tiene cantidades.
            </p>
          ),
      )}

      {mutation.isError && (
        <p className="text-sm text-red-600">
          {mutation.error instanceof Error ? mutation.error.message : 'No se pudo guardar el plan.'}
        </p>
      )}

      {resultado && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          <p>Plan guardado correctamente.</p>
          {resultado.advertencias.map((advertencia, indice) => (
            <p key={indice} className="text-amber-700">
              Entrega {advertencia.numero_entrega}: {advertencia.cantidad} no es múltiplo de{' '}
              {advertencia.unidades_por_presentacion} -- se sugiere {advertencia.cantidad_sugerida}.
            </p>
          ))}
        </div>
      )}

      <button
        type="button"
        disabled={hayDiferencias || hayEntregaVacia || mutation.isPending}
        onClick={guardar}
        className="rounded-md bg-navy px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {mutation.isPending ? 'Guardando…' : 'Guardar plan'}
      </button>
    </div>
  )
}

function Encabezado({ numeroOc, descartados }: { numeroOc: string; descartados: number }) {
  return (
    <header className="space-y-1">
      <h1 className="text-xl font-semibold text-slate-900">Planificación de entregas -- OC {numeroOc}</h1>
      {descartados > 0 && (
        <p className="text-xs text-slate-500">
          {descartados} renglón(es) descartado(s) en matching -- no entran en la planificación.
        </p>
      )}
    </header>
  )
}

interface FilaProps {
  renglon: RenglonPlanificacion
  n: number
  valores: number[]
  restante: number
  onCambiar: (indice: number, valor: number) => void
  onUsarSugerida: (indice: number, u: number) => void
}

function FilaPlanificacion({ renglon, n, valores, restante, onCambiar, onUsarSugerida }: FilaProps) {
  const etiqueta = etiquetaRenglonOc(renglon)
  const u = renglon.unidades_por_presentacion

  return (
    <tr className="border-t border-slate-100 align-top">
      <td className="p-2">
        <p className="text-xs font-medium text-slate-500">Renglón {etiqueta}</p>
        <p className="font-medium text-slate-900">{renglon.descripcion}</p>
        <p className="text-xs text-slate-500">
          Cant. {renglon.cantidad}
          {u ? ` — x${u}` : ''}
        </p>
      </td>
      {Array.from({ length: n }, (_, indice) => {
        const valor = valores[indice] ?? 0
        const noDivisible = !!u && valor % u !== 0
        return (
          <td key={indice} className="p-2">
            <input
              type="number"
              min={0}
              aria-label={`entrega ${indice + 1} renglón ${etiqueta}`}
              value={valor}
              onChange={(evento) => onCambiar(indice, Number(evento.target.value))}
              className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
            {noDivisible && u && (
              <p className="mt-1 text-xs text-amber-700">
                No es múltiplo de {u}.{' '}
                <button type="button" onClick={() => onUsarSugerida(indice, u)} className="underline">
                  usar {sugerirCantidadDivisible(valor, u)}
                </button>
              </p>
            )}
          </td>
        )
      })}
      <td className={`p-2 text-sm ${restante !== 0 ? 'font-medium text-red-600' : 'text-slate-500'}`}>
        {restante}
      </td>
    </tr>
  )
}

function PlanBloqueadoTabla({
  renglones,
  planActual,
}: {
  renglones: RenglonPlanificacion[]
  planActual: EntregaPlanOut[]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr>
            <th className="p-2 text-left">Renglón</th>
            {planActual.map((entrega) => (
              <th key={entrega.numero_entrega} className="p-2 text-left">
                Entrega {entrega.numero_entrega} ({entrega.estado})
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {renglones.map((renglon) => (
            <tr key={renglon.oc_item_id} className="border-t border-slate-100">
              <td className="p-2">
                <p className="text-xs font-medium text-slate-500">Renglón {etiquetaRenglonOc(renglon)}</p>
                <p className="font-medium text-slate-900">{renglon.descripcion}</p>
              </td>
              {planActual.map((entrega) => (
                <td key={entrega.numero_entrega} className="p-2">
                  {cantidadEnEntrega(entrega, renglon.oc_item_id)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
