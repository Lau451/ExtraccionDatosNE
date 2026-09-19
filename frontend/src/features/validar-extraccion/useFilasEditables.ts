import { useEffect, useMemo, useState } from 'react'

type CampoTipo = 'entero' | 'texto' | 'texto-opcional' | 'decimal' | 'decimal-positivo'

export interface CampoConfig {
  campo: string
  tipo: CampoTipo
  /** `false` -> columna de solo referencia (D6/D13.1: `numero_renglon`,
   * `entregas`, `_archivo`, `_extraction_id`): se muestra en la tabla pero un
   * click no abre `CeldaEditable`, y nunca aporta a `erroresPorCelda`. Default
   * (ausente) es `true` -- retrocompatible con licitación/comparativa, que no
   * declaran esta propiedad. */
  editable?: boolean
}

/** Mismos campos/orden que `services/presupuestacion/extraccion/models.py`
 * (`FilaLicitacionIn`/`FilaComparativaIn`) y que la validación de
 * `_validar_filas_override` en el service (design.md §3) -- espejo deliberado
 * en el cliente para que el usuario vea el error antes de mandar el request.
 *
 * `orden_compra` (Phase 8, D6/D13.1): las columnas de cabecera
 * (`numero_oc`/`fecha_emision`/`direccion_entrega`/etc.) NO están acá --
 * `CabeceraOrdenCompra` las edita una sola vez para todo el grupo, no por
 * fila (D13.1). Acá van solo las columnas de renglón: `numero_renglon`
 * (referencia visual, C10, nunca editable ni obligatoria), `descripcion`/
 * `cantidad`/`precio_unitario` (lo que de verdad viaja en `FilaOrdenCompraIn`)
 * y las columnas sintéticas/de referencia `entregas`/`_archivo`/
 * `_extraction_id` que `_leer_filas_grupo()` agrega para que el operador vea
 * de dónde vino cada renglón (D13), pero que tampoco se envían. */
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
  orden_compra: [
    { campo: 'numero_renglon', tipo: 'texto-opcional', editable: false },
    { campo: 'descripcion', tipo: 'texto' },
    { campo: 'cantidad', tipo: 'decimal' },
    { campo: 'precio_unitario', tipo: 'decimal-positivo' },
    { campo: 'entregas', tipo: 'texto-opcional', editable: false },
    { campo: '_archivo', tipo: 'texto-opcional', editable: false },
    { campo: '_extraction_id', tipo: 'texto-opcional', editable: false },
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

  if (tipo === 'decimal-positivo') {
    // Espejo del lado cliente de `_validar_orden_compra_override` (D6/D7):
    // `precio_unitario` es obligatorio y estrictamente positivo -- "vacío
    // bloquea confirmación" y "0" no es un precio válido.
    const normalizadoPositivo = limpio.replace(',', '.')
    const decimalPositivo = Number(normalizadoPositivo)
    if (!limpio || Number.isNaN(decimalPositivo)) return 'Debe ser un número válido'
    if (decimalPositivo <= 0) return 'Debe ser mayor a cero'
    return null
  }

  // decimal -- mismo normalizado "," -> "." que hace hoy _materializar_comparativa
  const normalizado = limpio.replace(',', '.')
  const decimal = Number(normalizado)
  if (!limpio || Number.isNaN(decimal)) return 'Debe ser un número válido'
  if (decimal < 0) return 'No puede ser negativo'
  return null
}

export interface PlanEntregaCsv {
  cantidad: string
  plazo_dias: number
}

/** Parser de la columna `entregas` del CSV de extracción (D6, gramática
 * definida en design.md § D6):
 *
 *   entregas   := plan ("|" plan)*
 *   plan       := cantidad "@" plazo_dias
 *   cantidad   := decimal con "." o "," como separador
 *   plazo_dias := entero >= 0
 *
 * `""` (o solo espacios) significa "el documento no declaró desglose para
 * esta línea" -- resultado válido, `[]`, sin error. Cualquier otra cosa que
 * no matchee la gramática devuelve `null` (distinto de `[]`: "declarado pero
 * roto", no "no declarado"). Puramente informativo/de referencia -- no viaja
 * en `FilaOrdenCompraIn` (el plan de entregas real lo arma `EntregasEditor`,
 * D8). */
export function parsearPlanEntregas(valor: string): PlanEntregaCsv[] | null {
  const limpio = (valor ?? '').trim()
  if (!limpio) return []

  const resultado: PlanEntregaCsv[] = []
  for (const plan of limpio.split('|')) {
    const partes = plan.split('@')
    if (partes.length !== 2) return null

    const cantidad = (partes[0] ?? '').trim()
    const plazoTexto = (partes[1] ?? '').trim()

    if (!cantidad || Number.isNaN(Number(cantidad.replace(',', '.')))) return null
    if (!/^\d+$/.test(plazoTexto)) return null

    resultado.push({ cantidad, plazo_dias: Number(plazoTexto) })
  }
  return resultado
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
      campos.forEach(({ campo, tipo, editable }) => {
        // Columnas de referencia (editable: false) nunca aportan error: el
        // usuario no puede corregirlas desde la tabla (D13.1).
        if (editable === false) return
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
