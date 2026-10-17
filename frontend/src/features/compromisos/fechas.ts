// Fechas de calendario como 'YYYY-MM-DD' y meses como 'YYYY-MM'. La aritmética
// se hace en UTC sobre Date.UTC: new Date('YYYY-MM-DD') también es UTC, pero
// formatearlo en hora local (UTC-3) mostraría el día anterior.

const ZONA_ARGENTINA = 'America/Argentina/Buenos_Aires'
const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]
const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']

function aUtc(iso: string): Date {
  const [anio, mes, dia] = iso.split('-').map(Number)
  return new Date(Date.UTC(anio, mes - 1, dia))
}

function aIso(fecha: Date): string {
  return fecha.toISOString().slice(0, 10)
}

function partes(iso: string): { anio: number; mes: number; dia: number } {
  const [anio, mes, dia] = iso.split('-').map(Number)
  return { anio, mes, dia }
}

/** Misma referencia que el backend: la fecha de hoy en Buenos Aires. */
export function hoyBuenosAires(): string {
  // en-CA formatea como YYYY-MM-DD.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: ZONA_ARGENTINA,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

export function sumarDias(iso: string, dias: number): string {
  const fecha = aUtc(iso)
  fecha.setUTCDate(fecha.getUTCDate() + dias)
  return aIso(fecha)
}

/** 0 = lunes … 6 = domingo. */
export function indiceDiaSemana(iso: string): number {
  return (aUtc(iso).getUTCDay() + 6) % 7
}

export function inicioSemana(iso: string): string {
  return sumarDias(iso, -indiceDiaSemana(iso))
}

export function diasDeSemana(inicio: string): string[] {
  return Array.from({ length: 7 }, (_, i) => sumarDias(inicio, i))
}

export function mesDe(iso: string): string {
  return iso.slice(0, 7)
}

export function sumarMeses(mes: string, cantidad: number): string {
  const [anio, numero] = mes.split('-').map(Number)
  const indice = anio * 12 + (numero - 1) + cantidad
  return `${Math.floor(indice / 12)}-${String((indice % 12) + 1).padStart(2, '0')}`
}

/** Semanas completas (lunes a domingo) que cubren el mes: de 4 a 6. */
export function semanasDelMes(mes: string): string[][] {
  const ultimo = sumarDias(`${sumarMeses(mes, 1)}-01`, -1)
  const semanas: string[][] = []
  for (let inicio = inicioSemana(`${mes}-01`); inicio <= ultimo; inicio = sumarDias(inicio, 7)) {
    semanas.push(diasDeSemana(inicio))
  }
  return semanas
}

export function nombreMes(mes: string): string {
  return MESES[Number(mes.slice(5, 7)) - 1]
}

export function etiquetaMes(mes: string): string {
  const nombre = nombreMes(mes)
  return `${nombre[0].toUpperCase()}${nombre.slice(1)} ${mes.slice(0, 4)}`
}

/** "19 – 25 de octubre 2026", "28 sep – 4 oct 2026", "28 dic 2026 – 3 ene 2027". */
export function etiquetaSemana(inicio: string): string {
  const a = partes(inicio)
  const b = partes(sumarDias(inicio, 6))
  if (a.anio !== b.anio) {
    return `${a.dia} ${MESES_CORTOS[a.mes - 1]} ${a.anio} – ${b.dia} ${MESES_CORTOS[b.mes - 1]} ${b.anio}`
  }
  if (a.mes !== b.mes) {
    return `${a.dia} ${MESES_CORTOS[a.mes - 1]} – ${b.dia} ${MESES_CORTOS[b.mes - 1]} ${b.anio}`
  }
  return `${a.dia} – ${b.dia} de ${MESES[a.mes - 1]} ${a.anio}`
}

export function diaSemanaLargo(iso: string): string {
  return DIAS[indiceDiaSemana(iso)]
}

export function fechaDiaMes(iso: string): string {
  const { mes, dia } = partes(iso)
  return `${dia} de ${MESES[mes - 1]}`
}

export function fechaCorta(iso: string): string {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
}
