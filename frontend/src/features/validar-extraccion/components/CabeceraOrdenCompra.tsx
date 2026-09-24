import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'

export interface CabeceraOrdenCompraValores {
  numero_oc: string
  fecha_emision: string
  direccion_entrega: string
  /** T2: notas libres de la OC -- editable, precargada igual que el resto de
   * la cabecera. Viaja como `OrdenCompraOverride.notas` en
   * `construirOrdenCompraOverride()` (`ValidarExtraccionDetalle.tsx`). */
  observaciones: string
}

interface Props {
  /** Filas concatenadas del grupo (`FilasExtraccionOut.filas`, D13) -- cada
   * fila trae `_extraction_id` (D6/D13). Solo se usa la primera fila de cada
   * miembro, igual que `_filas_representativas_por_miembro` en el backend. */
  filas: Record<string, string>[]
  /** Se dispara en cada cambio (montaje incluido) con la cabecera editable
   * actual y si está bloqueada. Espejo del contrato de `OrdenCompraSelector`
   * (`onClienteConfirmado`): quien renderiza el "Confirmar OC" real (Phase 8)
   * decide qué hacer con `bloqueado`. */
  onCambio: (cabecera: CabeceraOrdenCompraValores, bloqueado: boolean) => void
}

// Mismo criterio que `_CAMPOS_CABECERA_ADVERTENCIA` en
// services/presupuestacion/extraccion/service.py -- todo lo que NO sea
// numero_oc solo advierte, nunca bloquea (D13.1).
const CAMPOS_ADVERTENCIA: { campo: string; etiqueta: string }[] = [
  { campo: 'razon_social_cliente', etiqueta: 'Razón social' },
  { campo: 'cuit_cliente', etiqueta: 'CUIT' },
  { campo: 'fecha_emision', etiqueta: 'Fecha de emisión' },
  { campo: 'direccion_entrega', etiqueta: 'Dirección de entrega' },
  { campo: 'cantidad_entregas', etiqueta: 'Cantidad de entregas' },
  { campo: 'observaciones', etiqueta: 'Observaciones' }, // T2
]

/** Espejo de `_valor_mas_frecuente` (empate -> gana el primer miembro). */
function valorMasFrecuente(valores: string[]): string {
  const conteo = new Map<string, number>()
  for (const valor of valores) conteo.set(valor, (conteo.get(valor) ?? 0) + 1)
  let mejorValor = valores[0] ?? ''
  let mejorConteo = 0
  for (const valor of valores) {
    const conteoValor = conteo.get(valor) ?? 0
    if (conteoValor > mejorConteo) {
      mejorValor = valor
      mejorConteo = conteoValor
    }
  }
  return mejorValor
}

/** Espejo de `_filas_representativas_por_miembro`: una fila por
 * `_extraction_id`, en el orden en que aparecen. */
function representativasPorMiembro(filas: Record<string, string>[]): Record<string, string>[] {
  const vistos = new Set<string>()
  const representativas: Record<string, string>[] = []
  for (const fila of filas) {
    const extractionId = fila._extraction_id ?? ''
    if (!vistos.has(extractionId)) {
      vistos.add(extractionId)
      representativas.push(fila)
    }
  }
  return representativas
}

/** Cabecera única editable para todo el grupo (D13.1): precargada con el
 * valor más frecuente entre miembros, campos en desacuerdo marcados. Solo
 * `numero_oc` bloquea la confirmación -- identifica de forma unívoca a la OC
 * (D5); el resto es una advertencia que el usuario puede ignorar. */
export function CabeceraOrdenCompra({ filas, onCambio }: Props) {
  const representativas = useMemo(() => representativasPorMiembro(filas), [filas])

  const valoresNumeroOc = representativas.map((fila) => fila.numero_oc ?? '')
  const hayDesacuerdoNumeroOc = new Set(valoresNumeroOc).size > 1

  const [numeroOc, setNumeroOc] = useState(() => valorMasFrecuente(valoresNumeroOc))
  const [numeroOcEditado, setNumeroOcEditado] = useState(false)
  const [fechaEmision, setFechaEmision] = useState(() =>
    valorMasFrecuente(representativas.map((fila) => fila.fecha_emision ?? '')),
  )
  const [direccionEntrega, setDireccionEntrega] = useState(() =>
    valorMasFrecuente(representativas.map((fila) => fila.direccion_entrega ?? '')),
  )
  const [observaciones, setObservaciones] = useState(() =>
    valorMasFrecuente(representativas.map((fila) => fila.observaciones ?? '')),
  )

  // "Editarlo a un valor único lo habilita": cualquier edición explícita del
  // campo deja un único valor cargado, que es justamente lo que se necesita
  // para desbloquear -- no importa si coincide con alguno de los miembros.
  const bloqueado = hayDesacuerdoNumeroOc && !numeroOcEditado

  useEffect(() => {
    onCambio(
      {
        numero_oc: numeroOc,
        fecha_emision: fechaEmision,
        direccion_entrega: direccionEntrega,
        observaciones,
      },
      bloqueado,
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numeroOc, fechaEmision, direccionEntrega, observaciones, bloqueado])

  const advertencias = CAMPOS_ADVERTENCIA.filter(
    ({ campo }) => new Set(representativas.map((fila) => fila[campo] ?? '')).size > 1,
  )

  return (
    <div className="space-y-3 rounded-md border border-slate-200 p-3">
      <div>
        <label className="mb-1 block text-sm text-slate-600" htmlFor="cabecera-numero-oc">
          Número de OC
        </label>
        <input
          id="cabecera-numero-oc"
          value={numeroOc}
          onChange={(event) => {
            setNumeroOc(event.target.value)
            setNumeroOcEditado(true)
          }}
          className={clsx(
            'w-full rounded-md border px-3 py-2 text-sm',
            bloqueado ? 'border-red-500 text-red-600' : 'border-slate-300',
          )}
        />
        {bloqueado && (
          <p className="mt-1 text-xs text-red-600">
            Los archivos del grupo declaran números de OC distintos (
            {[...new Set(valoresNumeroOc)].sort().join(', ')}) -- corregí el valor antes de
            confirmar.
          </p>
        )}
      </div>

      <div>
        <label className="mb-1 block text-sm text-slate-600" htmlFor="cabecera-fecha-emision">
          Fecha de emisión
        </label>
        <input
          id="cabecera-fecha-emision"
          value={fechaEmision}
          onChange={(event) => setFechaEmision(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm text-slate-600" htmlFor="cabecera-direccion-entrega">
          Dirección de entrega
        </label>
        <input
          id="cabecera-direccion-entrega"
          value={direccionEntrega}
          onChange={(event) => setDireccionEntrega(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm text-slate-600" htmlFor="cabecera-observaciones">
          Observaciones
        </label>
        <textarea
          id="cabecera-observaciones"
          value={observaciones}
          onChange={(event) => setObservaciones(event.target.value)}
          rows={3}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      {advertencias.length > 0 && (
        <p className="text-xs text-amber-600">
          Desacuerdo entre archivos del grupo en: {advertencias.map((a) => a.etiqueta).join(', ')}.
          Se precargó el valor más frecuente -- revisá antes de confirmar.
        </p>
      )}
    </div>
  )
}
