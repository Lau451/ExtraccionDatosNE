import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  agruparExtracciones,
  desagruparExtracciones,
  listarExtracciones,
  type ExtraccionResumen,
} from '@/lib/api/extracciones'
import { PendientesTable } from './components/PendientesTable'

const EXTRACCIONES_KEY = ['extracciones', { validado: false }]

/** D13 § Agrupar después -- guard puro que espeja las precondiciones de
 * `agrupar_extracciones` (service.py): al menos 2 filas, todas del mismo
 * document_type. La UI real solo deja tildar filas orden_compra (ver
 * PendientesTable), así que "tipos mixtos" es defensivo acá, pero la función
 * se testea aparte de la integración con la tabla. */
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

export function ValidarExtraccionListado() {
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set())
  // Override optimista post-acción (ver grupoIdDe) -- null significa
  // "desagrupada en esta sesión", string significa "agrupada en esta sesión".
  const [gruposLocales, setGruposLocales] = useState<Record<string, string | null>>({})

  // D-VALIDAREXTRACCION (design.md §9.3) -- POST /procesar persiste en un
  // BackgroundTask del lado de `services/extraccion`; un usuario que sube un
  // documento y navega directo acá puede no verlo todavía. staleTime: 0 +
  // refetchOnWindowFocus (default de TanStack Query) + botón "Actualizar"
  // cubren el caso sin polling -- ver conclusión doble en design.md.
  const query = useQuery({
    queryKey: EXTRACCIONES_KEY,
    queryFn: () => listarExtracciones({ validado: false }),
    staleTime: 0,
  })

  const filas = query.data ?? []
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

  const puedeDesagrupar =
    filasSeleccionadas.length >= 1 &&
    filasSeleccionadas.every((extraccion) => grupoIdDe(extraccion, gruposLocales) !== null)

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Validar extracción</h1>
          <p className="text-sm text-slate-500">Extracciones pendientes de revisión</p>
        </div>
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
          <button
            type="button"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {query.isFetching ? 'Actualizando…' : 'Actualizar'}
          </button>
        </div>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {query.isPending && <p className="text-sm text-slate-500">Cargando…</p>}

        {query.isError && (
          <p className="text-sm text-red-600">
            {query.error instanceof Error ? query.error.message : 'No se pudo cargar el listado.'}
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

        {query.data && (
          <PendientesTable
            extracciones={query.data}
            seleccionados={seleccionados}
            onAlternarSeleccion={alternarSeleccion}
            gruposLocales={gruposLocales}
          />
        )}
      </div>
    </div>
  )
}
