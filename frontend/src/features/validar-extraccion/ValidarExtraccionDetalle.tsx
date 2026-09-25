import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  obtenerFilasExtraccion,
  validarExtraccion,
  type FilaComparativaIn,
  type FilaLicitacionIn,
  type ValidarExtraccionPayload,
} from '@/lib/api/extracciones'
import { listarProcesosComerciales } from '@/lib/api/procesosComerciales'
import { CabeceraOrdenCompra, type CabeceraOrdenCompraValores } from './components/CabeceraOrdenCompra'
import { ConfirmarValidacionDialog } from './components/ConfirmarValidacionDialog'
import { DocumentoDemasiadoGrande } from './components/DocumentoDemasiadoGrande'
import { OrdenCompraSelector } from './components/OrdenCompraSelector'
import { ProcesoComercialSelector } from './components/ProcesoComercialSelector'
import { TablaEditable } from './components/TablaEditable'
import { MAX_FILAS_EDITABLES } from './constants'
import { useFilasEditables } from './useFilasEditables'

const EXTRACCIONES_KEY = ['extracciones'] as const

/** D6: el extractor normaliza `fecha_emision` a `DD/MM/AAAA`. El backend la
 * tipa como `date` (Pydantic v2 solo acepta ISO `YYYY-MM-DD` para strings) --
 * sin esta conversión, cualquier fecha detectada rompería la confirmación con
 * un 422. `null`/vacío/formato inesperado -> `null` (el backend cae a la
 * fecha de confirmación por default, D6). */
function fechaCsvAIso(valor: string): string | null {
  const limpio = (valor ?? '').trim()
  const coincidencia = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(limpio)
  if (!coincidencia) return null
  const [, dia, mes, anio] = coincidencia
  return `${anio}-${mes}-${dia}`
}

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

  // Estado de la rama orden_compra (D3/D8/D13.1) -- cada componente de las
  // Phases 6/7 reporta su estado por callback (`onClienteConfirmado`/
  // `onCambio`), el container (acá) es quien decide `puedeConfirmar` y arma
  // el payload final, igual que ya hace con `procesoComercialId`.
  const [clienteId, setClienteId] = useState<string | null>(null)
  const [razonSocialExtraida, setRazonSocialExtraida] = useState<string | null>(null)
  const [cabecera, setCabecera] = useState<CabeceraOrdenCompraValores | null>(null)
  const [cabeceraBloqueada, setCabeceraBloqueada] = useState(false)

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
  const esOrdenCompra = filasQuery.data?.document_type === 'orden_compra'

  const mutation = useMutation({
    mutationFn: (payload: ValidarExtraccionPayload) => validarExtraccion(extractionId, payload),
    onSuccess: (resultado) => {
      queryClient.invalidateQueries({ queryKey: EXTRACCIONES_KEY })
      // D10: mismo patrón que subir -> validar (carga-documentos) -- la fase
      // siguiente (matching OC<->presupuesto) se abre sola en vez de dejar al
      // operador de vuelta en el listado sin saber que falta un paso.
      // `orden_compra_id` es null para licitación/comparativa (el mecanismo
      // no aplica), que conservan la navegación de siempre.
      if (resultado.orden_compra_id) {
        navigate({
          to: '/ordenes-compra/$ordenCompraId/matching',
          params: { ordenCompraId: resultado.orden_compra_id },
        })
        return
      }
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
          onConfirmarSinEditar={() =>
            mutation.mutate({ proceso_comercial_id: procesoComercialId, filas: null })
          }
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

  /** Arma `OrdenCompraOverride` (design.md § Interfaces) desde el estado del
   * container + el estado de `useFilasEditables`. `numero_renglon_documento`
   * viaja tal cual el documento lo declaró (o `null` si vino vacío, C10) --
   * nunca es lo que se persiste como `oc_items.numero_renglon` (D13.1, lo
   * asigna el backend por posición). `producto_id` queda `null`: no hay
   * selector de producto en esta pantalla (D11, fuera de alcance de Phase 8). */
  function construirOrdenCompraOverride() {
    return {
      numero_oc: cabecera?.numero_oc ?? '',
      cliente_id: clienteId ?? '',
      razon_social_extraida: razonSocialExtraida,
      fecha_emision: fechaCsvAIso(cabecera?.fecha_emision ?? ''),
      direccion_entrega: cabecera?.direccion_entrega || null,
      notas: (cabecera?.observaciones ?? '').trim() || null, // T2
      filas: hook.filas
        .filter((fila) => !fila._borrada)
        .map((fila) => ({
          numero_renglon_documento: String(fila.numero_renglon ?? '').trim() || null,
          descripcion: String(fila.descripcion ?? ''),
          cantidad: String(fila.cantidad ?? ''),
          precio_unitario: String(fila.precio_unitario ?? ''),
          producto_id: null,
        })),
    }
  }

  const puedeConfirmar = esOrdenCompra
    ? !hook.tieneErrores && clienteId !== null && !cabeceraBloqueada
    : !hook.tieneErrores && procesoComercialId !== null

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Validar extracción</h1>
        <p className="text-sm text-slate-500">
          {filasQuery.data.filas_leidas} filas leídas del documento
        </p>
      </header>

      {esOrdenCompra ? (
        <>
          <CabeceraOrdenCompra
            filas={filasQuery.data.filas}
            onCambio={(valores, bloqueado) => {
              setCabecera(valores)
              setCabeceraBloqueada(bloqueado)
            }}
          />
          <OrdenCompraSelector
            extractionId={extractionId}
            onClienteConfirmado={(id, razonSocial) => {
              setClienteId(id)
              setRazonSocialExtraida(razonSocial)
            }}
            onClienteDesconfirmado={() => {
              setClienteId(null)
              setRazonSocialExtraida(null)
            }}
          />
        </>
      ) : (
        <ProcesoComercialSelector
          documentType={filasQuery.data.document_type}
          procesoComercialId={procesoComercialId}
          procesos={procesosQuery.data ?? []}
          onChange={setProcesoComercialId}
        />
      )}

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
          esOrdenCompra
            ? mutation.mutate({ orden_compra: construirOrdenCompraOverride() })
            : mutation.mutate({
                proceso_comercial_id: procesoComercialId,
                filas: hook.filasParaEnviar() as unknown as FilaLicitacionIn[] | FilaComparativaIn[],
              })
        }
      />
    </div>
  )
}
