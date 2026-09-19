import { useEffect, useMemo, useState } from 'react'

export interface FilaParaEntregas {
  descripcion: string
  cantidad: string
}

/** Espejo de `EntregaPlanIn` (services/presupuestacion/extraccion/models.py):
 * `cantidades_por_posicion: null` -> reparto automático (D8). */
export interface EntregaPlanEditable {
  numero_entrega: number
  plazo_dias: number | null
  cantidades_por_posicion: Record<string, string> | null
}

interface Props {
  filas: FilaParaEntregas[]
  onCambio: (entregas: EntregaPlanEditable[], bloqueado: boolean) => void
}

function aNumero(valor: string): number {
  const parseado = Number((valor ?? '').trim().replace(',', '.'))
  return Number.isFinite(parseado) ? parseado : 0
}

/** Espejo de `repartir_cantidad` (D8, `services/presupuestacion/extraccion/service.py`):
 * entero -> las primeras `resto` entregas reciben `base + 1`, el resto `base`;
 * decimal -> las primeras N-1 entregas reciben la parte entera truncada a
 * centésimos, la última se lleva el resto (para no arrastrar el error de
 * redondeo). Devuelve strings, igual que el override que viaja al backend. */
function repartirCantidad(cantidad: number, entregas: number): string[] {
  if (entregas < 1) return []
  if (Number.isInteger(cantidad)) {
    const base = Math.floor(cantidad / entregas)
    const resto = cantidad % entregas
    return Array.from({ length: entregas }, (_, indice) =>
      String(indice < resto ? base + 1 : base),
    )
  }
  const base = Math.floor((cantidad / entregas) * 100) / 100
  const partes = Array.from({ length: entregas - 1 }, () => base)
  const ultima = Math.round((cantidad - base * (entregas - 1)) * 100) / 100
  return [...partes.map((parte) => String(parte)), String(ultima)]
}

/** Entregas del plan de una OC (D8): cantidad de entregas + plazo por
 * entrega + desglose opcional por línea, con validación en vivo que espeja
 * `_validar_orden_compra_override` -- mismo mensaje de error por renglón. */
export function EntregasEditor({ filas, onCambio }: Props) {
  const [cantidadEntregas, setCantidadEntregas] = useState(1)
  const [plazos, setPlazos] = useState<(number | null)[]>([null])
  const [desgloseManual, setDesgloseManual] = useState(false)
  const [cantidadesPorEntrega, setCantidadesPorEntrega] = useState<Record<string, string>[]>([{}])

  function cambiarCantidadEntregas(valor: number) {
    const n = Math.max(1, Math.trunc(valor) || 1)
    setCantidadEntregas(n)
    setPlazos((previo) => Array.from({ length: n }, (_, i) => previo[i] ?? null))
    setCantidadesPorEntrega((previo) => Array.from({ length: n }, (_, i) => previo[i] ?? {}))
  }

  const repartoAutomatico = useMemo(
    () => filas.map((fila) => repartirCantidad(aNumero(fila.cantidad), cantidadEntregas)),
    [filas, cantidadEntregas],
  )

  const errores = useMemo(() => {
    if (!desgloseManual) return []
    const mensajes: string[] = []
    filas.forEach((fila, indiceFila) => {
      const posicion = indiceFila + 1
      const clave = String(posicion)
      const suma = cantidadesPorEntrega.reduce(
        (acumulado, entrega) => acumulado + aNumero(entrega[clave] ?? '0'),
        0,
      )
      const cantidadFila = aNumero(fila.cantidad)
      if (suma !== cantidadFila) {
        mensajes.push(
          `renglón ${posicion}: la suma de las entregas (${suma}) no coincide con la cantidad del renglón (${cantidadFila})`,
        )
      }
    })
    return mensajes
  }, [desgloseManual, filas, cantidadesPorEntrega])

  const bloqueado = errores.length > 0

  useEffect(() => {
    const entregas: EntregaPlanEditable[] = Array.from({ length: cantidadEntregas }, (_, indice) => ({
      numero_entrega: indice + 1,
      plazo_dias: plazos[indice] ?? null,
      cantidades_por_posicion: desgloseManual ? (cantidadesPorEntrega[indice] ?? {}) : null,
    }))
    onCambio(entregas, bloqueado)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cantidadEntregas, plazos, desgloseManual, cantidadesPorEntrega, bloqueado])

  return (
    <div className="space-y-3 rounded-md border border-slate-200 p-3">
      <div>
        <label className="mb-1 block text-sm text-slate-600" htmlFor="entregas-cantidad">
          Cantidad de entregas
        </label>
        <input
          id="entregas-cantidad"
          type="number"
          min={1}
          value={cantidadEntregas}
          onChange={(event) => cambiarCantidadEntregas(Number(event.target.value))}
          className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input
          type="checkbox"
          checked={desgloseManual}
          onChange={(event) => setDesgloseManual(event.target.checked)}
        />
        Desglosar cantidad por línea manualmente
      </label>

      {!desgloseManual && (
        <div data-testid="reparto-automatico" className="space-y-1 text-sm text-slate-600">
          <p>Reparto automático parejo:</p>
          {filas.map((fila, indiceFila) => (
            <p key={indiceFila}>
              {fila.descripcion}: {repartoAutomatico[indiceFila]?.join(' / ')}
            </p>
          ))}
        </div>
      )}

      {desgloseManual && (
        <div className="space-y-3">
          {filas.map((fila, indiceFila) => {
            const posicion = indiceFila + 1
            return (
              <div key={indiceFila} className="space-y-1">
                <p className="text-xs font-medium text-slate-500">
                  {fila.descripcion} (cantidad {fila.cantidad})
                </p>
                <div className="flex flex-wrap gap-2">
                  {Array.from({ length: cantidadEntregas }, (_, indiceEntrega) => (
                    <input
                      key={indiceEntrega}
                      aria-label={`entrega ${indiceEntrega + 1} renglón ${posicion}`}
                      value={cantidadesPorEntrega[indiceEntrega]?.[String(posicion)] ?? ''}
                      onChange={(event) => {
                        const valor = event.target.value
                        setCantidadesPorEntrega((previo) => {
                          const copia = previo.map((entrega) => ({ ...entrega }))
                          copia[indiceEntrega] = { ...copia[indiceEntrega], [String(posicion)]: valor }
                          return copia
                        })
                      }}
                      className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {errores.length > 0 && (
        <ul className="space-y-1 text-xs text-red-600">
          {errores.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
