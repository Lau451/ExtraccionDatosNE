import type { FilaImportPresupuestoLegacy, ProcesoComercialLegacy } from '@/lib/api/pcp'

export interface ErrorParseoCsv {
  linea: number
  mensaje: string
}

export interface ResultadoParseoCsvPresupuestos {
  filas: FilaImportPresupuestoLegacy[]
  errores: ErrorParseoCsv[]
}

/** Columnas obligatorias del export legado (feature doc `Decisions`):
 * ausentes del encabezado, el parseo se corta sin intentar leer filas. */
const COLUMNAS_REQUERIDAS = [
  'codigo_cliente',
  'razon_social_cliente',
  'numero_presupuesto',
  'renglon',
  'descripcion_producto',
  'cantidad_producto',
] as const

const COLUMNAS_OPCIONALES = [
  'proceso_comercial',
  'fecha_generacion',
  'codigo_producto',
  'precio_producto',
  'importe_total',
] as const

const FECHA_ISO = /^(\d{4})-(\d{2})-(\d{2})$/
const FECHA_DDMMYYYY = /^(\d{2})\/(\d{2})\/(\d{4})$/

interface FilaTokenizada {
  valores: string[]
  /** Línea física (1-based) donde empieza este registro, contando saltos de
   * línea embebidos dentro de campos entre comillas -- no solo el índice del
   * registro tokenizado. */
  lineaInicio: number
}

/** Comilla abierta que nunca se cierra en el resto del archivo: el parseo se
 * corta ahí y no se procesa nada (ni antes ni después de esa línea) en vez de
 * absorber silenciosamente el resto del contenido dentro del campo. */
class ErrorComillasSinCerrar extends Error {
  readonly linea: number

  constructor(linea: number) {
    super(`Comillas sin cerrar a partir de la línea ${linea}`)
    this.linea = linea
  }
}

/** Tokeniza el contenido completo (no línea por línea) para poder soportar
 * comillas con delimitador/salto de línea embebidos, RFC4180-style. Lleva la
 * cuenta de la línea física real (`lineaActual`) para que un salto de línea
 * embebido en un campo entre comillas también cuente, y así los registros
 * siguientes reporten su línea física correcta. */
function tokenizarCsv(contenido: string, delimitador: string): FilaTokenizada[] {
  const filas: FilaTokenizada[] = []
  let fila: string[] = []
  let campo = ''
  let dentroDeComillas = false
  let i = 0
  let lineaActual = 1
  let lineaInicioFila = 1
  let lineaInicioComillas = 1

  while (i < contenido.length) {
    const char = contenido[i]

    if (char === '\r' || char === '\n') {
      const esCrLf = char === '\r' && contenido[i + 1] === '\n'
      if (dentroDeComillas) {
        campo += char
        if (esCrLf) campo += contenido[i + 1]
        i += esCrLf ? 2 : 1
        lineaActual += 1
        continue
      }
      fila.push(campo)
      filas.push({ valores: fila, lineaInicio: lineaInicioFila })
      fila = []
      campo = ''
      i += esCrLf ? 2 : 1
      lineaActual += 1
      lineaInicioFila = lineaActual
      continue
    }

    if (dentroDeComillas) {
      if (char === '"') {
        if (contenido[i + 1] === '"') {
          campo += '"'
          i += 2
          continue
        }
        dentroDeComillas = false
        i += 1
        continue
      }
      campo += char
      i += 1
      continue
    }

    if (char === '"') {
      dentroDeComillas = true
      lineaInicioComillas = lineaActual
      i += 1
      continue
    }

    if (char === delimitador) {
      fila.push(campo)
      campo = ''
      i += 1
      continue
    }

    campo += char
    i += 1
  }

  if (dentroDeComillas) {
    throw new ErrorComillasSinCerrar(lineaInicioComillas)
  }

  if (campo.length > 0 || fila.length > 0) {
    fila.push(campo)
    filas.push({ valores: fila, lineaInicio: lineaInicioFila })
  }

  return filas
}

function esFilaVacia(fila: string[]): boolean {
  return fila.every((campo) => campo.trim() === '')
}

/** Delimitador auto-detectado a partir de la primera línea del archivo,
 * contando ocurrencias fuera de comillas de `;` y `,` (Decisions). Si ninguno
 * aparece (o empatan) usa `,` por default. */
function detectarDelimitador(primeraLinea: string): string {
  let dentroDeComillas = false
  let comas = 0
  let puntoYComa = 0
  for (const char of primeraLinea) {
    if (char === '"') {
      dentroDeComillas = !dentroDeComillas
      continue
    }
    if (dentroDeComillas) continue
    if (char === ',') comas += 1
    if (char === ';') puntoYComa += 1
  }
  return puntoYComa > comas ? ';' : ','
}

type ResultadoNumero = { ok: true; valor: number | undefined } | { ok: false }

/** Acepta coma decimal y espacios; un valor con `.` y `,` a la vez es
 * ambiguo (no se adivina separador de miles) y se reporta como error. */
function parsearNumeroDecimal(valorCrudo: string): ResultadoNumero {
  const valor = valorCrudo.trim()
  if (valor === '') return { ok: true, valor: undefined }
  const sinEspacios = valor.replace(/\s/g, '')
  if (sinEspacios.includes('.') && sinEspacios.includes(',')) return { ok: false }
  const normalizado = sinEspacios.includes(',') ? sinEspacios.replace(',', '.') : sinEspacios
  const numero = Number(normalizado)
  if (Number.isNaN(numero)) return { ok: false }
  return { ok: true, valor: numero }
}

function parsearEntero(valorCrudo: string): number | null {
  const valor = valorCrudo.trim()
  if (!/^-?\d+$/.test(valor)) return null
  return Number(valor)
}

type ResultadoFecha = { ok: true; valor: string | undefined } | { ok: false }

/** Valida que año/mes/día formen una fecha de calendario real (mes 1-12,
 * día dentro de la cantidad de días de ese mes/año -- incluye años
 * bisiestos vía `Date`, no un tope fijo de 31). */
function esFechaCalendarioValida(anio: number, mes: number, dia: number): boolean {
  if (mes < 1 || mes > 12 || dia < 1) return false
  const ultimoDiaDelMes = new Date(anio, mes, 0).getDate()
  return dia <= ultimoDiaDelMes
}

/** `fecha_generacion` acepta dd/mm/aaaa o ISO y siempre se envía en ISO
 * (Decisions). Valida que sea una fecha de calendario real (no solo el
 * formato): rechaza días fuera de rango del mes (31/02), meses fuera de
 * rango (2026-13-45) y 29/02 en años no bisiestos. */
function normalizarFecha(valorCrudo: string): ResultadoFecha {
  const valor = valorCrudo.trim()
  if (valor === '') return { ok: true, valor: undefined }

  const coincidenciaIso = FECHA_ISO.exec(valor)
  if (coincidenciaIso) {
    const [, yyyy, mm, dd] = coincidenciaIso
    if (!esFechaCalendarioValida(Number(yyyy), Number(mm), Number(dd))) return { ok: false }
    return { ok: true, valor }
  }

  const coincidenciaDdmmyyyy = FECHA_DDMMYYYY.exec(valor)
  if (!coincidenciaDdmmyyyy) return { ok: false }
  const [, dd, mm, yyyy] = coincidenciaDdmmyyyy
  if (!esFechaCalendarioValida(Number(yyyy), Number(mm), Number(dd))) return { ok: false }
  return { ok: true, valor: `${yyyy}-${mm}-${dd}` }
}

/** Parsea el CSV del export legado de presupuestos (Progress) en el browser
 * -- feature doc `presupuestos-legacy-import-ui.md` Decisions. Función pura:
 * sin dependencias nuevas, sin acceso a red/DOM más allá del string recibido
 * (el caller lee el `File` con `.text()` antes de invocarla). */
export function parsearCsvPresupuestos(contenidoOriginal: string): ResultadoParseoCsvPresupuestos {
  const contenido = contenidoOriginal.replace(/^﻿/, '')

  if (contenido.trim() === '') {
    return { filas: [], errores: [{ linea: 1, mensaje: 'El archivo está vacío' }] }
  }

  const primerSalto = contenido.search(/\r\n|\r|\n/)
  const primeraLinea = primerSalto === -1 ? contenido : contenido.slice(0, primerSalto)
  const delimitador = detectarDelimitador(primeraLinea)

  let filasTokenizadas: FilaTokenizada[]
  try {
    filasTokenizadas = tokenizarCsv(contenido, delimitador)
  } catch (error) {
    if (error instanceof ErrorComillasSinCerrar) {
      return { filas: [], errores: [{ linea: error.linea, mensaje: error.message }] }
    }
    throw error
  }
  while (filasTokenizadas.length > 0 && esFilaVacia(filasTokenizadas[filasTokenizadas.length - 1].valores)) {
    filasTokenizadas.pop()
  }

  if (filasTokenizadas.length === 0) {
    return { filas: [], errores: [{ linea: 1, mensaje: 'El archivo está vacío' }] }
  }

  const encabezado = filasTokenizadas[0].valores.map((columna) => columna.trim().toLowerCase())
  const indiceDe = (nombre: string) => encabezado.indexOf(nombre)

  const columnasFaltantes = COLUMNAS_REQUERIDAS.filter((columna) => indiceDe(columna) === -1)
  if (columnasFaltantes.length > 0) {
    return {
      filas: [],
      errores: columnasFaltantes.map((columna) => ({
        linea: 1,
        mensaje: `Falta la columna requerida "${columna}"`,
      })),
    }
  }

  const idx = Object.fromEntries(
    [...COLUMNAS_REQUERIDAS, ...COLUMNAS_OPCIONALES].map((columna) => [columna, indiceDe(columna)]),
  ) as Record<(typeof COLUMNAS_REQUERIDAS)[number] | (typeof COLUMNAS_OPCIONALES)[number], number>

  const filas: FilaImportPresupuestoLegacy[] = []
  const errores: ErrorParseoCsv[] = []

  for (let i = 1; i < filasTokenizadas.length; i += 1) {
    const columnas = filasTokenizadas[i].valores
    if (esFilaVacia(columnas)) continue
    const linea = filasTokenizadas[i].lineaInicio
    const valor = (indice: number) => (indice === -1 ? '' : (columnas[indice] ?? '').trim())

    const erroresFila: string[] = []

    const codigoCliente = valor(idx.codigo_cliente)
    if (codigoCliente === '') erroresFila.push('falta codigo_cliente')

    const razonSocialCliente = valor(idx.razon_social_cliente)

    const numeroPresupuesto = valor(idx.numero_presupuesto)
    if (numeroPresupuesto === '') erroresFila.push('falta numero_presupuesto')

    const descripcionProducto = valor(idx.descripcion_producto)
    if (descripcionProducto === '') erroresFila.push('falta descripcion_producto')

    const renglon = parsearEntero(valor(idx.renglon))
    if (renglon === null) erroresFila.push('renglón no es un número entero')

    const cantidad = parsearNumeroDecimal(valor(idx.cantidad_producto))
    if (!cantidad.ok || cantidad.valor === undefined) erroresFila.push('cantidad_producto no es numérica')

    const precio = parsearNumeroDecimal(valor(idx.precio_producto))
    if (!precio.ok) erroresFila.push('precio_producto no es numérico')

    const importeTotal = parsearNumeroDecimal(valor(idx.importe_total))
    if (!importeTotal.ok) erroresFila.push('importe_total no es numérico')

    const fecha = normalizarFecha(valor(idx.fecha_generacion))
    if (!fecha.ok) erroresFila.push('fecha_generacion inválida (use dd/mm/aaaa o aaaa-mm-dd)')

    const procesoComercialCrudo = valor(idx.proceso_comercial)
    let procesoComercial: ProcesoComercialLegacy | undefined
    if (procesoComercialCrudo === '') {
      procesoComercial = undefined
    } else if (procesoComercialCrudo === '1' || procesoComercialCrudo === '2') {
      procesoComercial = procesoComercialCrudo
    } else {
      erroresFila.push('proceso_comercial debe ser 1 o 2')
    }

    if (erroresFila.length > 0) {
      errores.push({ linea, mensaje: erroresFila.join('; ') })
      continue
    }

    filas.push({
      codigo_cliente: codigoCliente,
      razon_social_cliente: razonSocialCliente,
      numero_presupuesto: numeroPresupuesto,
      proceso_comercial: procesoComercial,
      fecha_generacion: fecha.ok ? fecha.valor : undefined,
      renglon: renglon as number,
      codigo_producto: valor(idx.codigo_producto) || undefined,
      descripcion_producto: descripcionProducto,
      cantidad_producto: cantidad.ok ? (cantidad.valor as number) : 0,
      precio_producto: precio.ok ? precio.valor : undefined,
      importe_total: importeTotal.ok ? importeTotal.valor : undefined,
    })
  }

  return { filas, errores }
}
