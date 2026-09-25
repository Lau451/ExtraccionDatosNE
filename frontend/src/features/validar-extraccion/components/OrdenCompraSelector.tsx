import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { obtenerClienteCandidato } from '@/lib/api/extracciones'
import type { Tercero } from '@/lib/api/terceros'
import { ClienteBuscador } from './ClienteBuscador'

interface Props {
  extractionId: string
  /** Se dispara SOLO por el click explícito de "Confirmar cliente" (nivel 1/2)
   * o al elegir un resultado del buscador manual (nivel 3) -- nunca por
   * mostrar la sugerencia sola (design.md § D3: "el gate humano es el mismo
   * en los tres niveles"). `razonSocialExtraida` es lo que se aprende en
   * `oc_cliente_alias` al confirmar (D3.1); `null` cuando el cliente vino del
   * buscador manual, no de una sugerencia con texto de origen. */
  onClienteConfirmado: (clienteId: string, razonSocialExtraida: string | null) => void
  /** "Cambiar" deshace la confirmación: quien renderiza debe volver a
   * bloquear "Confirmar OC" hasta una nueva confirmación explícita. */
  onClienteDesconfirmado?: () => void
}

function etiquetaCliente(razonSocial: string, cuit: string | null | undefined) {
  return cuit ? `${razonSocial} — CUIT ${cuit}` : razonSocial
}

/** Rediseño completo de D3: sugiere el cliente en 3 niveles (alias -> CUIT ->
 * búsqueda manual) pero nunca ancla sola -- la confirmación es siempre un
 * click humano explícito, igual en los tres niveles. Sin input de código: esa
 * premisa quedó invalidada por C5 (el `codigo_interno` es nuestro, no del
 * cliente). */
export function OrdenCompraSelector({
  extractionId,
  onClienteConfirmado,
  onClienteDesconfirmado,
}: Props) {
  const [mostrarBuscador, setMostrarBuscador] = useState(false)
  const [candidatoElegidoId, setCandidatoElegidoId] = useState<string | null>(null)
  // Etiqueta del cliente ya confirmado: sin esto el click de "Confirmar
  // cliente" no daba ninguna señal visible (la confirmación vive en el padre).
  const [etiquetaConfirmada, setEtiquetaConfirmada] = useState<string | null>(null)

  const { data, isPending } = useQuery({
    queryKey: ['cliente-candidato', extractionId],
    queryFn: () => obtenerClienteCandidato(extractionId),
  })

  if (isPending) {
    return <p className="text-sm text-slate-500">Buscando cliente sugerido…</p>
  }

  if (!data) {
    return null
  }

  const confirmar = (clienteId: string, razonSocialExtraida: string | null, etiqueta: string) => {
    setEtiquetaConfirmada(etiqueta)
    onClienteConfirmado(clienteId, razonSocialExtraida)
  }

  if (etiquetaConfirmada) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border border-emerald-300 bg-emerald-50 p-3">
        <div>
          <p className="text-sm text-emerald-700">Cliente confirmado</p>
          <p className="text-sm font-medium text-slate-900">{etiquetaConfirmada}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setEtiquetaConfirmada(null)
            onClienteDesconfirmado?.()
          }}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700"
        >
          Cambiar
        </button>
      </div>
    )
  }

  const seleccionarManual = (tercero: Tercero) => {
    confirmar(tercero.id, null, etiquetaCliente(tercero.razon_social, tercero.cuit))
  }

  // Nivel 3 (D3.2): sin sugerencia, o el usuario rechazó la que había.
  if (mostrarBuscador || data.origen === 'ninguno') {
    return <ClienteBuscador onSeleccionar={seleccionarManual} />
  }

  // Nivel 2 con CUIT compartido (C6): lista de candidatos, ninguno
  // preseleccionado -- acá sí hay ambigüedad real que solo el humano resuelve.
  if (data.origen === 'cuit_compartido') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          Varias sedes comparten el CUIT {data.cuit_extraido}. Elegí la que corresponde:
        </p>
        <fieldset className="space-y-2">
          {data.candidatos.map((candidato) => (
            <label
              key={candidato.cliente_id}
              className="flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm"
            >
              <input
                type="radio"
                name="candidato-cuit-compartido"
                value={candidato.cliente_id}
                checked={candidatoElegidoId === candidato.cliente_id}
                onChange={() => setCandidatoElegidoId(candidato.cliente_id)}
              />
              <span>
                {candidato.razon_social}
                {candidato.cuit ? ` — CUIT ${candidato.cuit}` : ''}
              </span>
            </label>
          ))}
        </fieldset>
        <button
          type="button"
          disabled={!candidatoElegidoId}
          onClick={() => {
            const elegido = data.candidatos.find((c) => c.cliente_id === candidatoElegidoId)
            if (elegido) {
              confirmar(
                elegido.cliente_id,
                data.razon_social_extraida,
                etiquetaCliente(elegido.razon_social, elegido.cuit),
              )
            }
          }}
          className="rounded-md bg-navy px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Confirmar cliente
        </button>
      </div>
    )
  }

  // Nivel 1 (alias) o Nivel 2 (CUIT exclusivo): una única sugerencia,
  // preseleccionada visualmente pero sin confirmar hasta el click humano.
  const [sugerencia] = data.candidatos

  return (
    <div className="space-y-2 rounded-md border border-slate-200 p-3">
      <p className="text-sm text-slate-600">Cliente sugerido:</p>
      <p className="text-sm font-medium text-slate-900">
        {sugerencia.razon_social}
        {sugerencia.cuit ? ` — CUIT ${sugerencia.cuit}` : ''}
        {!sugerencia.activo && ' (inactivo)'}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() =>
            confirmar(
              sugerencia.cliente_id,
              data.razon_social_extraida,
              etiquetaCliente(sugerencia.razon_social, sugerencia.cuit),
            )
          }
          className="rounded-md bg-navy px-4 py-2 text-sm font-medium text-white"
        >
          Confirmar cliente
        </button>
        <button
          type="button"
          onClick={() => setMostrarBuscador(true)}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
        >
          No es este
        </button>
      </div>
    </div>
  )
}
