import { useRef } from 'react'
import clsx from 'clsx'
import { importeNoCoincide, type CampoConfig, type FilaEditable } from '../useFilasEditables'
import { CeldaEditable } from './CeldaEditable'

const ETIQUETA_CAMPO: Record<string, string> = {
  item: 'Item',
  descripcion: 'Descripción',
  cantidad: 'Cantidad',
  renglon: 'Renglón',
  proveedor: 'Proveedor',
  marca: 'Marca',
  precio: 'Precio',
  // orden_compra (D6/D13.1, Phase 8)
  numero_renglon: 'N° renglón (documento)',
  precio_unitario: 'Precio unitario',
  importe_total: 'Importe total', // T2, control de línea
  entregas: 'Entregas (documento)',
  _archivo: 'Archivo',
  _extraction_id: 'Extracción',
}

interface Props {
  campos: CampoConfig[]
  filas: FilaEditable[]
  erroresPorCelda: Record<string, string>
  onActualizarCelda: (filaId: string, campo: string, valor: string) => void
  onRevertirCelda: (filaId: string, campo: string) => void
  onBorrarFila: (filaId: string) => void
  onAgregarFila: () => void
}

/** Presentational: grilla por document_type (design.md §9.2). Recibe el
 * estado de `useFilasEditables` por props -- el hook lo posee el container
 * (`ValidarExtraccionDetalle`). */
export function TablaEditable({
  campos,
  filas,
  erroresPorCelda,
  onActualizarCelda,
  onRevertirCelda,
  onBorrarFila,
  onAgregarFila,
}: Props) {
  // "Borrar" es un toggle (`_borrada: !fila._borrada` en el hook), no una baja
  // definitiva -- si la fila desaparece de la tabla apenas se la marca, ese
  // toggle queda inalcanzable: no hay forma de deshacer un click accidental
  // antes de confirmar. Se muestran todas las filas; las borradas quedan
  // tachadas con la opción de deshacer, y los inputs se deshabilitan para que
  // no se puedan seguir editando datos que no se van a enviar.
  const inputRefs = useRef(new Map<string, HTMLInputElement | null>())

  function enfocar(filaId: string, campo: string) {
    inputRefs.current.get(`${filaId}:${campo}`)?.focus()
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
            {campos.map((c) => (
              <th key={c.campo} className="px-3 py-2 font-medium">
                {ETIQUETA_CAMPO[c.campo] ?? c.campo}
              </th>
            ))}
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {filas.map((fila, filaIndex) => (
            <tr key={fila._id} className="border-b border-slate-100">
              {campos.map((c) => {
                const key = `${fila._id}:${c.campo}`
                const siguiente = filas[filaIndex + 1]
                const valor = String(fila[c.campo] ?? '')

                // Columnas de referencia (D6/D13.1: numero_renglon, entregas,
                // _archivo, _extraction_id) se muestran como texto plano -- un
                // click nunca abre un CeldaEditable, el usuario no puede
                // tocarlas desde acá.
                if (c.editable === false) {
                  // T2: control no bloqueante, solo para importe_total --
                  // nunca toca erroresPorCelda (eso seguiría bloqueando
                  // "Confirmar OC"), es puramente informativo (D13.1: solo
                  // numero_oc bloquea).
                  const importeNoCoincideEnFila = c.campo === 'importe_total' && importeNoCoincide(fila)
                  return (
                    <td key={c.campo} className="px-3 py-2 align-top">
                      <span
                        data-testid={key}
                        className={clsx(
                          'block px-2 py-1 text-sm text-slate-500',
                          importeNoCoincideEnFila && 'text-amber-600',
                          fila._borrada && 'line-through',
                        )}
                      >
                        {valor}
                      </span>
                      {importeNoCoincideEnFila && (
                        <p className="px-2 text-xs text-amber-600">
                          No coincide con cantidad × precio unitario
                        </p>
                      )}
                    </td>
                  )
                }

                return (
                  <td key={c.campo} className="px-3 py-2 align-top">
                    <CeldaEditable
                      fieldId={key}
                      label={`${ETIQUETA_CAMPO[c.campo] ?? c.campo} fila ${filaIndex + 1}`}
                      value={valor}
                      error={erroresPorCelda[key]}
                      disabled={fila._borrada}
                      onChange={(valor) => onActualizarCelda(fila._id, c.campo, valor)}
                      onEscape={() => onRevertirCelda(fila._id, c.campo)}
                      onEnter={() => siguiente && enfocar(siguiente._id, c.campo)}
                      inputRef={(el) => inputRefs.current.set(key, el)}
                    />
                  </td>
                )
              })}
              <td className="px-3 py-2 text-right align-top">
                <button
                  type="button"
                  aria-label={fila._borrada ? `Deshacer borrado de fila ${filaIndex + 1}` : `Borrar fila ${filaIndex + 1}`}
                  onClick={() => onBorrarFila(fila._id)}
                  className={clsx(
                    'text-xs font-medium hover:underline',
                    fila._borrada ? 'text-slate-500' : 'text-red-600',
                  )}
                >
                  {fila._borrada ? 'Deshacer' : 'Borrar'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="border-t border-slate-200 p-3">
        <button
          type="button"
          onClick={onAgregarFila}
          className="text-sm font-medium text-accent hover:underline"
        >
          + Agregar fila
        </button>
      </div>
    </div>
  )
}
