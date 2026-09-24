import { describe, expect, it } from 'vitest'
import { parsearCsvPresupuestos } from './parsearCsvPresupuestos'

const ENCABEZADO =
  'codigo_cliente;razon_social_cliente;numero_presupuesto;proceso_comercial;fecha_generacion;renglon;codigo_producto;descripcion_producto;cantidad_producto;precio_producto;importe_total;subtotal_renglon'

describe('parsearCsvPresupuestos', () => {
  it('parsea filas válidas con delimitador ; y valores completos', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;1;24/09/2026;1;PROD-1;Amoxicilina 500mg;10,5;125,50;1317,75;99',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas).toEqual([
      {
        codigo_cliente: 'CLI-1',
        razon_social_cliente: 'Farmacia Central',
        numero_presupuesto: 'PRE-100',
        proceso_comercial: '1',
        fecha_generacion: '2026-09-24',
        renglon: 1,
        codigo_producto: 'PROD-1',
        descripcion_producto: 'Amoxicilina 500mg',
        cantidad_producto: 10.5,
        precio_producto: 125.5,
        importe_total: 1317.75,
      },
    ])
  })

  it('ignora columnas desconocidas como subtotal_renglon', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;999',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas[0]).not.toHaveProperty('subtotal_renglon')
  })

  it('omite valores opcionales vacíos en vez de enviarlos como cadena vacía', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas[0]).toEqual({
      codigo_cliente: 'CLI-1',
      razon_social_cliente: 'Farmacia Central',
      numero_presupuesto: 'PRE-100',
      proceso_comercial: undefined,
      fecha_generacion: undefined,
      renglon: 1,
      codigo_producto: undefined,
      descripcion_producto: 'Amoxicilina 500mg',
      cantidad_producto: 10,
      precio_producto: undefined,
      importe_total: undefined,
    })
  })

  it('auto-detecta el delimitador , cuando el encabezado usa comas', () => {
    const csv = [
      'codigo_cliente,razon_social_cliente,numero_presupuesto,renglon,descripcion_producto,cantidad_producto',
      'CLI-2,Farmacia del Sur,PRE-200,1,Ibuprofeno 400mg,5',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas).toHaveLength(1)
    expect(resultado.filas[0].numero_presupuesto).toBe('PRE-200')
  })

  it('soporta campos entre comillas con el delimitador embebido', () => {
    const csv = [
      'codigo_cliente,razon_social_cliente,numero_presupuesto,renglon,descripcion_producto,cantidad_producto',
      'CLI-2,"Farmacia del Sur, Sucursal Norte",PRE-200,1,"Jarabe, sabor frutilla",5',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas[0].razon_social_cliente).toBe('Farmacia del Sur, Sucursal Norte')
    expect(resultado.filas[0].descripcion_producto).toBe('Jarabe, sabor frutilla')
  })

  it('acepta CRLF, BOM inicial y descarta líneas finales vacías', () => {
    const csv =
      '﻿' +
      [
        'codigo_cliente,razon_social_cliente,numero_presupuesto,renglon,descripcion_producto,cantidad_producto',
        'CLI-3,Farmacia Norte,PRE-300,1,Paracetamol 500mg,20',
        '',
        '',
      ].join('\r\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas).toHaveLength(1)
    expect(resultado.filas[0].codigo_cliente).toBe('CLI-3')
  })

  it('acepta fecha_generacion en formato ISO además de dd/mm/aaaa', () => {
    const csv = [
      'codigo_cliente,razon_social_cliente,numero_presupuesto,fecha_generacion,renglon,descripcion_producto,cantidad_producto',
      'CLI-1,Farmacia Central,PRE-100,2026-09-24,1,Amoxicilina 500mg,10',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.errores).toEqual([])
    expect(resultado.filas[0].fecha_generacion).toBe('2026-09-24')
  })

  it('reporta un error por columna requerida faltante en el encabezado, sin parsear filas', () => {
    const csv = [
      'codigo_cliente,razon_social_cliente,renglon,descripcion_producto,cantidad_producto',
      'CLI-1,Farmacia Central,1,Amoxicilina 500mg,10',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toEqual([
      { linea: 1, mensaje: 'Falta la columna requerida "numero_presupuesto"' },
    ])
  })

  it('reporta renglón no entero con el número de línea del CSV', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;;;abc;;Amoxicilina 500mg;10;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toEqual([{ linea: 2, mensaje: expect.stringMatching(/renglón/i) }])
  })

  it('reporta cantidad_producto no numérica', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;diez;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toEqual([{ linea: 2, mensaje: expect.stringMatching(/cantidad/i) }])
  })

  it('reporta un valor con punto y coma decimales a la vez como error, sin adivinar el separador de miles', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;1.250,50;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toEqual([{ linea: 2, mensaje: expect.stringMatching(/cantidad/i) }])
  })

  it('reporta codigo_cliente, numero_presupuesto y descripcion_producto faltantes', () => {
    const csv = [
      ENCABEZADO,
      ';Farmacia Central;;;;1;;;10;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toHaveLength(1)
    expect(resultado.errores[0].linea).toBe(2)
    expect(resultado.errores[0].mensaje).toMatch(/codigo_cliente/)
    expect(resultado.errores[0].mensaje).toMatch(/numero_presupuesto/)
    expect(resultado.errores[0].mensaje).toMatch(/descripcion_producto/)
  })

  it('acumula errores de varias filas conservando la numeración de línea original', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;',
      'CLI-2;Farmacia Sur;PRE-200;;;abc;;Ibuprofeno 400mg;5;;;',
      'CLI-3;Farmacia Norte;PRE-300;;;3;;Paracetamol 500mg;20;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toHaveLength(2)
    expect(resultado.filas.map((f) => f.codigo_cliente)).toEqual(['CLI-1', 'CLI-3'])
    expect(resultado.errores).toEqual([{ linea: 3, mensaje: expect.stringMatching(/renglón/i) }])
  })

  it('reporta proceso_comercial inválido cuando no es 1 ni 2', () => {
    const csv = [
      ENCABEZADO,
      'CLI-1;Farmacia Central;PRE-100;9;;1;;Amoxicilina 500mg;10;;;',
    ].join('\n')

    const resultado = parsearCsvPresupuestos(csv)

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toEqual([{ linea: 2, mensaje: expect.stringMatching(/proceso_comercial/i) }])
  })

  it('el archivo vacío reporta un único error de encabezado', () => {
    const resultado = parsearCsvPresupuestos('')

    expect(resultado.filas).toEqual([])
    expect(resultado.errores).toHaveLength(1)
  })
})
