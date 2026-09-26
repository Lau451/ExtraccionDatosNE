import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  agruparExtracciones,
  desagruparExtracciones,
  listarExtracciones,
  type DocumentType,
  type ExtraccionResumen,
} from '@/lib/api/extracciones'
import { ExtraccionesTable } from './components/ExtraccionesTable'
import { ESTADO_META, ESTADOS_DERIVADOS, estadoDerivadoDe, type EstadoDerivado } from './estadoExtraccion'

// T2 (validar-extraccion-organizacion) -- una tab por tipo de documento
// (decisión de usuario, 2026-09-26), en este orden fijo. La columna "Tipo"
// que tenía la tabla anterior (PendientesTable) se elimina: la tab activa ya
// comunica el tipo, mostrarlo también por fila era redundante.
const TIPOS_DOCUMENTO: readonly DocumentType[] = ['licitacion', 'cotizacion', 'comparativa', 'orden_compra']

const ETIQUETA_TIPO: Record<DocumentType, string> = {
  licitacion: 'Licitación',
  cotizacion: 'Directa',
  comparativa: 'Comparativa',
  orden_compra: 'Orden de compra',
}

type FiltroEstado = 'todos' | EstadoDerivado

// T2 (corrección post-review) -- SE PROBÓ un único query `limit:200` sin
// filtrar por `validado` y se revirtió: `GET /extracciones` ordena por
// `created_at DESC`, y las filas validadas se acumulan para siempre (nunca
// se borran) mientras comparten esa misma ventana con las pendientes. Pasado
// un cierto volumen (~200 filas más nuevas entre validadas y pendientes), una
// extracción PENDIENTE más vieja quedaba fuera de la página sin ningún aviso
// -- una regresión real frente al diseño previo, que sí separaba ambas
// consultas. Se vuelve al split de dos queries:
// - pendientes (`validado:false`): todo lo que todavía puede necesitar
//   revisión (processing/completed/partial/failed sin validar), con un
//   límite alto -- son las filas que de verdad importa no perder de vista.
// - validadas (`validado:true`): mismo tope de 50 que ya usaba el diseño
//   anterior (D11) para la sección "Órdenes de compra validadas", ahora
//   compartido por las 4 tabs en vez de reservado solo para OC. Una
//   droguería muy activa puede no ver TODAS sus validaciones viejas de todos
//   los tipos en esta pantalla -- mismo tipo de límite que ya existía, más
//   repartido.
const LIMITE_PENDIENTES = 200
const LIMITE_VALIDADAS = 50

function queryKeyExtracciones(validado: boolean, soloMias: boolean, limit: number) {
  return ['extracciones', { validado, soloMias, limit }] as const
}

/** D13 § Agrupar después -- guard puro que espeja las precondiciones de
 * `agrupar_extracciones` (service.py): al menos 2 filas, todas del mismo
 * document_type. La UI real solo deja tildar filas orden_compra en estado
 * validable (ver ExtraccionesTable), así que "tipos mixtos" es defensivo
 * acá, pero la función se testea aparte de la integración con la tabla. */
export function puedeAgruparSeleccion(seleccionadas: ExtraccionResumen[]): boolean {
  return (
    seleccionadas.length >= 2 &&
    seleccionadas.every((extraccion) => extraccion.document_type === 'orden_compra')
  )
}

/** 7.13 -- GET /extracciones ya expone `grupo_id` persistido. `gruposLocales`
 * pasa a ser solo un override OPTIMISTA: se completa recién después de un
 * agrupar/desagrupar exitoso en esta sesión, para no esperar el próximo
 * refetch. Mientras no haya override para una extracción, se usa el dato
 * persistido -- así el indicador y "Desagrupar" sobreviven a un
 * refetch/recarga de página sin haber pasado por la acción local primero. */
export function grupoIdDe(
  extraccion: ExtraccionResumen,
  gruposLocales: Record<string, string | null>,
): string | null {
  if (extraccion.id in gruposLocales) return gruposLocales[extraccion.id]
  return extraccion.grupo_id ?? null
}

function haySinTerminar(extracciones: ExtraccionResumen[]): boolean {
  return extracciones.some((extraccion) => extraccion.status === 'processing')
}

export function ValidarExtraccionListado() {
  const [tipoActivo, setTipoActivo] = useState<DocumentType>('licitacion')
  const [filtroEstado, setFiltroEstado] = useState<FiltroEstado>('todos')
  const [soloMias, setSoloMias] = useState(false)
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set())
  // Override optimista post-acción (ver grupoIdDe) -- null significa
  // "desagrupada en esta sesión", string significa "agrupada en esta sesión".
  const [gruposLocales, setGruposLocales] = useState<Record<string, string | null>>({})

  // D-VALIDAREXTRACCION (design.md §9.3) -- POST /procesar persiste en un
  // BackgroundTask del lado de `services/extraccion`; un usuario que sube un
  // documento y navega directo acá puede no verlo todavía. staleTime: 0 +
  // refetchOnWindowFocus (default de TanStack Query) + botón "Actualizar"
  // cubren ESE caso puntual sin polling (ver design.md, "conclusión doble").
  const pendientesQuery = useQuery({
    queryKey: queryKeyExtracciones(false, soloMias, LIMITE_PENDIENTES),
    queryFn: () =>
      listarExtracciones({
        validado: false,
        limit: LIMITE_PENDIENTES,
        ...(soloMias ? { solo_mias: true } : {}),
      }),
    staleTime: 0,
    // `refetchInterval` es un problema DISTINTO del anterior: con T1 el
    // listado puede mostrar filas 'processing' ya visibles en pantalla, y
    // sin polling el usuario tendría que apretar "Actualizar" a mano para
    // verlas avanzar a completed/failed -- mismo criterio ya usado en
    // `carga-documentos/components/RecentCard.tsx`. Se mantiene "modesto" y
    // CONDICIONAL: se apaga solo apenas no queda ninguna fila procesando.
    // Solo esta query puede tener filas 'processing' (una fila validada
    // nunca está en 'processing'), así que solo ella pollea.
    refetchInterval: (q) => (haySinTerminar(q.state.data ?? []) ? 5000 : false),
  })

  const validadasQuery = useQuery({
    queryKey: queryKeyExtracciones(true, soloMias, LIMITE_VALIDADAS),
    queryFn: () =>
      listarExtracciones({
        validado: true,
        limit: LIMITE_VALIDADAS,
        ...(soloMias ? { solo_mias: true } : {}),
      }),
    staleTime: 0,
  })

  const cargando = pendientesQuery.isPending || validadasQuery.isPending
  const datosListos = pendientesQuery.data !== undefined && validadasQuery.data !== undefined
  const errorQuery = pendientesQuery.error ?? validadasQuery.error
  const hayError = pendientesQuery.isError || validadasQuery.isError
  const actualizando = pendientesQuery.isFetching || validadasQuery.isFetching

  function actualizar() {
    pendientesQuery.refetch()
    validadasQuery.refetch()
  }

  // Merge de las dos queries -- una sola fuente para tabs/chips/counts/tabla.
  const filas = [...(pendientesQuery.data ?? []), ...(validadasQuery.data ?? [])]

  const filasPorTipo = filas.filter((extraccion) => extraccion.document_type === tipoActivo)
  const conteosPorEstado = ESTADOS_DERIVADOS.reduce(
    (acc, estado) => {
      acc[estado] = filasPorTipo.filter((extraccion) => estadoDerivadoDe(extraccion) === estado).length
      return acc
    },
    {} as Record<EstadoDerivado, number>,
  )
  const filasFiltradas =
    filtroEstado === 'todos'
      ? filasPorTipo
      : filasPorTipo.filter((extraccion) => estadoDerivadoDe(extraccion) === filtroEstado)

  const filasSeleccionadas = filas.filter((extraccion) => seleccionados.has(extraccion.id))

  const agruparMutation = useMutation({
    mutationFn: (ids: string[]) => agruparExtracciones(ids),
    onSuccess: (respuesta, ids) => {
      setGruposLocales((previo) => {
        const copia = { ...previo }
        for (const id of ids) copia[id] = respuesta.grupo_id
        return copia
      })
      setSeleccionados(new Set())
    },
  })

  const desagruparMutation = useMutation({
    mutationFn: (ids: string[]) => desagruparExtracciones(ids),
    onSuccess: (_data, ids) => {
      setGruposLocales((previo) => {
        const copia = { ...previo }
        for (const id of ids) copia[id] = null
        return copia
      })
      setSeleccionados(new Set())
    },
  })

  function alternarSeleccion(id: string) {
    setSeleccionados((previo) => {
      const copia = new Set(previo)
      if (copia.has(id)) copia.delete(id)
      else copia.add(id)
      return copia
    })
  }

  function cambiarTab(tipo: DocumentType) {
    setTipoActivo(tipo)
    setFiltroEstado('todos')
  }

  const puedeDesagrupar =
    filasSeleccionadas.length >= 1 &&
    filasSeleccionadas.every((extraccion) => grupoIdDe(extraccion, gruposLocales) !== null)

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-10">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Validar extracción</h1>
          <p className="text-sm text-slate-500">
            Extracciones de la droguería, organizadas por tipo de documento
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              aria-label="Solo mías"
              checked={soloMias}
              onChange={(evento) => setSoloMias(evento.target.checked)}
            />
            Solo mías
          </label>
          <button
            type="button"
            onClick={actualizar}
            disabled={actualizando}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {actualizando ? 'Actualizando…' : 'Actualizar'}
          </button>
        </div>
      </header>

      <div
        role="tablist"
        aria-label="Tipo de documento"
        className="flex gap-1 border-b border-slate-200"
      >
        {TIPOS_DOCUMENTO.map((tipo) => {
          const cantidad = filas.filter((extraccion) => extraccion.document_type === tipo).length
          const activo = tipo === tipoActivo
          return (
            <button
              key={tipo}
              type="button"
              role="tab"
              aria-selected={activo}
              onClick={() => cambiarTab(tipo)}
              className={
                activo
                  ? 'border-b-2 border-accent px-3 py-2 text-sm font-medium text-accent'
                  : 'border-b-2 border-transparent px-3 py-2 text-sm font-medium text-slate-500 hover:text-slate-700'
              }
            >
              {ETIQUETA_TIPO[tipo]} ({cantidad})
            </button>
          )
        })}
      </div>

      <div role="tabpanel" className="space-y-4">
        {tipoActivo === 'orden_compra' && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => desagruparMutation.mutate(Array.from(seleccionados))}
              disabled={!puedeDesagrupar || desagruparMutation.isPending}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Desagrupar
            </button>
            <button
              type="button"
              onClick={() => agruparMutation.mutate(Array.from(seleccionados))}
              disabled={!puedeAgruparSeleccion(filasSeleccionadas) || agruparMutation.isPending}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Agrupar seleccionadas como una sola OC
            </button>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            aria-pressed={filtroEstado === 'todos'}
            onClick={() => setFiltroEstado('todos')}
            className={
              filtroEstado === 'todos'
                ? 'rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-white'
                : 'rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200'
            }
          >
            Todos ({filasPorTipo.length})
          </button>
          {ESTADOS_DERIVADOS.map((estado) => (
            <button
              key={estado}
              type="button"
              aria-pressed={filtroEstado === estado}
              onClick={() => setFiltroEstado(estado)}
              className={
                filtroEstado === estado
                  ? 'rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-white'
                  : 'rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200'
              }
            >
              {ESTADO_META[estado].label} ({conteosPorEstado[estado]})
            </button>
          ))}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          {cargando && <p className="text-sm text-slate-500">Cargando…</p>}

          {hayError && (
            <p className="text-sm text-red-600">
              {errorQuery instanceof Error ? errorQuery.message : 'No se pudo cargar el listado.'}
            </p>
          )}

          {agruparMutation.isError && (
            <p className="text-sm text-red-600">
              {agruparMutation.error instanceof Error
                ? agruparMutation.error.message
                : 'No se pudo agrupar la selección.'}
            </p>
          )}

          {desagruparMutation.isError && (
            <p className="text-sm text-red-600">
              {desagruparMutation.error instanceof Error
                ? desagruparMutation.error.message
                : 'No se pudo desagrupar la selección.'}
            </p>
          )}

          {datosListos && (
            <ExtraccionesTable
              extracciones={filasFiltradas}
              tipoActivo={tipoActivo}
              seleccionados={seleccionados}
              onAlternarSeleccion={alternarSeleccion}
              gruposLocales={gruposLocales}
            />
          )}
        </div>
      </div>
    </div>
  )
}
