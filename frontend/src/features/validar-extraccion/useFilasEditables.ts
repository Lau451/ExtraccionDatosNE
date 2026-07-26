import { useEffect, useMemo, useState } from 'react'

type CampoTipo = 'entero' | 'texto' | 'texto-opcional' | 'decimal'

export interface CampoConfig {
  campo: string
  tipo: CampoTipo
}

/** Mismos campos/orden que `services/presupuestacion/extraccion/models.py`
 * (`FilaLicitacionIn`/`FilaComparativaIn`) y que la validación de
 * `_validar_filas_override` en el service (design.md §3) -- espejo deliberado
 * en el cliente para que el usuario vea el error antes de mandar el request. */
const CAMPOS_POR_DOCUMENT_TYPE: Record<string, CampoConfig[]> = {
  comparativa: [
    { campo: 'renglon', tipo: 'entero' },
    { campo: 'proveedor', tipo: 'texto' },
    { campo: 'marca', tipo: 'texto-opcional' },
    { campo: 'precio', tipo: 'decimal' },
  ],
  licitacion: [
    { campo: 'item', tipo: 'entero' },
    { campo: 'descripcion', tipo: 'texto' },
    { campo: 'cantidad', tipo: 'decimal' },
  ],
  cotizacion: [
    { campo: 'item', tipo: 'entero' },
    { campo: 'descripcion', tipo: 'texto' },
    { campo: 'cantidad', tipo: 'decimal' },
  ],
}

export interface FilaEditable {
  _id: string
  _nueva: boolean
  _borrada: boolean
  [campo: string]: string | boolean
}

function validarCampo(tipo: CampoTipo, valor: string): string | null {
  const limpio = (valor ?? '').trim()

  if (tipo === 'texto-opcional') return null

  if (tipo === 'entero') {
    if (!limpio || !/^-?\d+$/.test(limpio)) return 'Debe ser un número entero'
    if (Number(limpio) <= 0) return 'Debe ser mayor a cero'
    return null
  }

  if (tipo === 'texto') {
    if (!limpio) return 'No puede estar vacío'
    return null
  }

  // decimal -- mismo normalizado "," -> "." que hace hoy _materializar_comparativa
  const normalizado = limpio.replace(',', '.')
  const decimal = Number(normalizado)
  if (!limpio || Number.isNaN(decimal)) return 'Debe ser un número válido'
  if (decimal < 0) return 'No puede ser negativo'
  return null
}

let contadorFilaNueva = 0
function idFilaNueva() {
  contadorFilaNueva += 1
  return `nueva-${contadorFilaNueva}`
}

/** Estado local de la tabla editable: diff contra el server (modificadas/
 * borradas/agregadas) + validación por celda (design.md §9.2). `filasOriginales`
 * es inmutable -- solo se lee para el diff y para `revertirCelda`. */
export function useFilasEditables(
  documentType: string,
  filasOriginales: Record<string, string>[] | undefined,
) {
  const campos = CAMPOS_POR_DOCUMENT_TYPE[documentType] ?? []

  const [filas, setFilas] = useState<FilaEditable[]>([])

  // `filasOriginales` llega async (React Query): mientras la query está
  // pendiente vale `undefined` -- una sola referencia primitiva estable, no un
  // array nuevo por render, así que este efecto NO se dispara en cada render
  // (Object.is(undefined, undefined) === true). Se dispara una sola vez,
  // cuando pasa de `undefined` al array real cacheado por React Query.
  // (Ojo: el caller NO debe pasar `?? []` -- eso crea un array nuevo por
  // render y este mismo efecto entraría en loop infinito de renders.)
  useEffect(() => {
    if (!filasOriginales) return
    setFilas(
      filasOriginales.map((fila, indice) => ({
        ...fila,
        _id: `original-${indice}`,
        _nueva: false,
        _borrada: false,
      })),
    )
  }, [filasOriginales])

  const originalesPorId = useMemo(() => {
    const mapa = new Map<string, Record<string, string>>()
    filasOriginales?.forEach((fila, indice) => mapa.set(`original-${indice}`, fila))
    return mapa
  }, [filasOriginales])

  function actualizarCelda(filaId: string, campo: string, valor: string) {
    setFilas((actuales) =>
      actuales.map((fila) => (fila._id === filaId ? { ...fila, [campo]: valor } : fila)),
    )
  }

  function revertirCelda(filaId: string, campo: string) {
    const original = originalesPorId.get(filaId)
    if (!original) return
    actualizarCelda(filaId, campo, original[campo] ?? '')
  }

  function borrarFila(filaId: string) {
    setFilas((actuales) =>
      actuales.map((fila) => (fila._id === filaId ? { ...fila, _borrada: !fila._borrada } : fila)),
    )
  }

  function agregarFila() {
    const filaVacia: FilaEditable = { _id: idFilaNueva(), _nueva: true, _borrada: false }
    campos.forEach(({ campo }) => {
      filaVacia[campo] = ''
    })
    setFilas((actuales) => [...actuales, filaVacia])
  }

  const erroresPorCelda = useMemo(() => {
    const errores: Record<string, string> = {}
    filas.forEach((fila) => {
      if (fila._borrada) return
      campos.forEach(({ campo, tipo }) => {
        const mensaje = validarCampo(tipo, String(fila[campo] ?? ''))
        if (mensaje) errores[`${fila._id}:${campo}`] = mensaje
      })
    })
    return errores
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filas, documentType])

  const modificadas = filas.filter((fila) => {
    if (fila._nueva || fila._borrada) return false
    const original = originalesPorId.get(fila._id)
    if (!original) return false
    return campos.some(({ campo }) => String(fila[campo] ?? '') !== (original[campo] ?? ''))
  }).length

  const borradas = filas.filter((fila) => fila._borrada && !fila._nueva).length
  const agregadas = filas.filter((fila) => fila._nueva && !fila._borrada).length

  function filasParaEnviar(): Record<string, string>[] {
    return filas
      .filter((fila) => !fila._borrada)
      .map((fila) => {
        const plano: Record<string, string> = {}
        campos.forEach(({ campo }) => {
          plano[campo] = String(fila[campo] ?? '')
        })
        return plano
      })
  }

  return {
    filas,
    campos,
    modificadas,
    borradas,
    agregadas,
    erroresPorCelda,
    tieneErrores: Object.keys(erroresPorCelda).length > 0,
    actualizarCelda,
    revertirCelda,
    borrarFila,
    agregarFila,
    filasParaEnviar,
  }
}
