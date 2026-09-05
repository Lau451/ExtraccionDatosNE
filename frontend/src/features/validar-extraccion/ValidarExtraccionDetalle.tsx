import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  obtenerFilasExtraccion,
  validarExtraccion,
  type FilaComparativaIn,
  type FilaLicitacionIn,
} from '@/lib/api/extracciones'
import { listarProcesosComerciales } from '@/lib/api/procesosComerciales'
import { ConfirmarValidacionDialog } from './components/ConfirmarValidacionDialog'
import { DocumentoDemasiadoGrande } from './components/DocumentoDemasiadoGrande'
import { ProcesoComercialSelector } from './components/ProcesoComercialSelector'
import { TablaEditable } from './components/TablaEditable'
import { MAX_FILAS_EDITABLES } from './constants'
import { useFilasEditables } from './useFilasEditables'

const EXTRACCIONES_KEY = ['extracciones'] as const

interface Props {
  extractionId: string
  /** row_count conocido desde el listado (search param de la ruta, ver
   * routes/_authenticated.validar-extraccion.$extractionId.tsx). Permite
   * decidir el gate D7 SIN llamar a /filas primero (design.md §7: "gate duro
   * antes de pedir las filas"). Si llega en 0 (navegación directa sin pasar
   * por el listado), el backend igual protege: FilasExtraccionOut ya viene con
   * editable=false + filas=[] cuando filas_leidas > 500. */
  rowCountHint: number
}

export function ValidarExtraccionDetalle({ extractionId, rowCountHint }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [procesoComercialId, setProcesoComercialId] = useState<string | null>(null)
  const [confirmando, setConfirmando] = useState(false)

  const bloqueadoPorHint = rowCountHint > MAX_FILAS_EDITABLES

  const filasQuery = useQuery({
    queryKey: [...EXTRACCIONES_KEY, extractionId, 'filas'],
    queryFn: () => obtenerFilasExtraccion(extractionId),
    enabled: !bloqueadoPorHint,
  })

  const procesosQuery = useQuery({
    queryKey: ['procesos-comerciales'],
    queryFn: listarProcesosComerciales,
    enabled: !bloqueadoPorHint,
  })

  const hook = useFilasEditables(filasQuery.data?.document_type ?? '', filasQuery.data?.filas)

  const mutation = useMutation({
    // Unión de listas, no lista de uniones (mismo criterio que el backend,
    // design.md §2.1) -- filasParaEnviar() siempre es homogénea en runtime,
    // una sola llamada nunca mezcla document_type.
    mutationFn: (filas: FilaLicitacionIn[] | FilaComparativaIn[] | null) =>
      validarExtraccion(extractionId, {
        proceso_comercial_id: procesoComercialId,
        filas,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: EXTRACCIONES_KEY })
      navigate({ to: '/validar-extraccion' })
    },
  })

  // Bloqueado por el hint del listado, o por la red de seguridad del server
  // (editable=false cuando filas_leidas > 500 aunque el hint no haya llegado).
  const bloqueadoPorServidor = filasQuery.data ? !filasQuery.data.editable : false
  if (bloqueadoPorHint || bloqueadoPorServidor) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 px-6 py-10">
        <h1 className="text-xl font-semibold text-slate-900">Validar extracción</h1>
        <DocumentoDemasiadoGrande
          rowCount={filasQuery.data?.row_count ?? rowCountHint}
          isPending={mutation.isPending}
          onConfirmarSinEditar={() => mutation.mutate(null)}
        />
        {mutation.isError && (
          <p className="text-sm text-red-600">
            {mutation.error instanceof Error ? mutation.error.message : 'No se pudo validar.'}
          </p>
        )}
      </div>
    )
  }

  if (filasQuery.isPending) {
    return <div className="px-6 py-10 text-sm text-slate-500">Cargando filas…</div>
  }

  if (filasQuery.isError || !filasQuery.data) {
    return (
      <div className="px-6 py-10 text-sm text-red-600">
        {filasQuery.error instanceof Error
          ? filasQuery.error.message
          : 'No se pudieron cargar las filas de esta extracción.'}
      </div>
    )
  }

  const puedeConfirmar = !hook.tieneErrores && procesoComercialId !== null

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Validar extracción</h1>
        <p className="text-sm text-slate-500">
          {filasQuery.data.filas_leidas} filas leídas del documento
        </p>
      </header>

      <ProcesoComercialSelector
        documentType={filasQuery.data.document_type}
        procesoComercialId={procesoComercialId}
        procesos={procesosQuery.data ?? []}
        onChange={setProcesoComercialId}
      />

      <TablaEditable
        campos={hook.campos}
        filas={hook.filas}
        erroresPorCelda={hook.erroresPorCelda}
        onActualizarCelda={hook.actualizarCelda}
        onRevertirCelda={hook.revertirCelda}
        onBorrarFila={hook.borrarFila}
        onAgregarFila={hook.agregarFila}
      />

      {mutation.isError && (
        <p className="text-sm text-red-600">
          {mutation.error instanceof Error ? mutation.error.message : 'No se pudo validar.'}
        </p>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          disabled={!puedeConfirmar}
          onClick={() => setConfirmando(true)}
          className="rounded-md bg-navy px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Confirmar validación
        </button>
      </div>

      <ConfirmarValidacionDialog
        open={confirmando}
        onOpenChange={setConfirmando}
        modificadas={hook.modificadas}
        borradas={hook.borradas}
        agregadas={hook.agregadas}
        documentType={filasQuery.data.document_type}
        isPending={mutation.isPending}
        onConfirm={() =>
          mutation.mutate(
            hook.filasParaEnviar() as unknown as FilaLicitacionIn[] | FilaComparativaIn[],
          )
        }
      />
    </div>
  )
}
