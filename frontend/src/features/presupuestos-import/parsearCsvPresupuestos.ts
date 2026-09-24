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

const FECHA_ISO = /^\d{4}-\d{2}-\d{2}$/
const FECHA_DDMMYYYY = /^(\d{2})\/(\d{2})\/(\d{4})$/

/** Tokeniza el contenido completo (no línea por línea) para poder soportar
 * comillas con delimitador/salto de línea embebidos, RFC4180-style. */
function tokenizarCsv(contenido: string, delimitador: string): string[][] {
  const filas: string[][] = []
  let fila: string[] = []
  let campo = ''
  let dentroDeComillas = false
  let i = 0

  while (i < contenido.length) {
    const char = contenido[i]

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
      i += 1
      continue
    }

    if (char === delimitador) {
      fila.push(campo)
      campo = ''
      i += 1
      continue
    }

    if (char === '\r' || char === '\n') {
      fila.push(campo)
      filas.push(fila)
      fila = []
      campo = ''
      i += char === '\r' && contenido[i + 1] === '\n' ? 2 : 1
      continue
    }

    campo += char
    i += 1
  }

  if (campo.length > 0 || fila.length > 0) {
    fila.push(campo)
    filas.push(fila)
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

/** `fecha_generacion` acepta dd/mm/aaaa o ISO y siempre se envía en ISO
 * (Decisions). */
function normalizarFecha(valorCrudo: string): ResultadoFecha {
  const valor = valorCrudo.trim()
  if (valor === '') return { ok: true, valor: undefined }
  if (FECHA_ISO.test(valor)) return { ok: true, valor }
  const coincidencia = FECHA_DDMMYYYY.exec(valor)
  if (!coincidencia) return { ok: false }
  const [, dd, mm, yyyy] = coincidencia
  const mes = Number(mm)
  const dia = Number(dd)
  if (mes < 1 || mes > 12 || dia < 1 || dia > 31) return { ok: false }
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

  const filasTokenizadas = tokenizarCsv(contenido, delimitador)
  while (filasTokenizadas.length > 0 && esFilaVacia(filasTokenizadas[filasTokenizadas.length - 1])) {
    filasTokenizadas.pop()
  }

  if (filasTokenizadas.length === 0) {
    return { filas: [], errores: [{ linea: 1, mensaje: 'El archivo está vacío' }] }
  }

  const encabezado = filasTokenizadas[0].map((columna) => columna.trim().toLowerCase())
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
    const columnas = filasTokenizadas[i]
    if (esFilaVacia(columnas)) continue
    const linea = i + 1
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
