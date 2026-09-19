import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { parsearPlanEntregas, useFilasEditables } from './useFilasEditables'

const FILAS_LICITACION = [
  { item: '1', descripcion: 'Paracetamol', cantidad: '10' },
  { item: '2', descripcion: 'Ibuprofeno', cantidad: '5' },
]

describe('useFilasEditables', () => {
  it('arranca sin modificadas, borradas ni agregadas, y sin errores', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    expect(result.current.modificadas).toBe(0)
    expect(result.current.borradas).toBe(0)
    expect(result.current.agregadas).toBe(0)
    expect(result.current.erroresPorCelda).toEqual({})
    expect(result.current.tieneErrores).toBe(false)
  })

  it('cuenta una fila como modificada cuando cambia un campo', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    const filaId = result.current.filas[0]._id
    act(() => result.current.actualizarCelda(filaId, 'cantidad', '20'))
    expect(result.current.modificadas).toBe(1)
    expect(result.current.borradas).toBe(0)
    expect(result.current.agregadas).toBe(0)
  })

  it('cuenta una fila como borrada y la excluye de filasParaEnviar', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    const filaId = result.current.filas[0]._id
    act(() => result.current.borrarFila(filaId))
    expect(result.current.borradas).toBe(1)
    expect(result.current.filasParaEnviar()).toHaveLength(1)
  })

  it('cuenta una fila agregada y no la marca como modificada', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    act(() => result.current.agregarFila())
    expect(result.current.agregadas).toBe(1)
    expect(result.current.modificadas).toBe(0)
    expect(result.current.filas).toHaveLength(3)
    expect(result.current.filasParaEnviar()).toHaveLength(3)
  })

  it('reporta erroresPorCelda para valores inválidos en filas de licitación', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    const filaId = result.current.filas[0]._id
    act(() => result.current.actualizarCelda(filaId, 'cantidad', 'no-numero'))
    expect(result.current.erroresPorCelda[`${filaId}:cantidad`]).toBeDefined()
    expect(result.current.tieneErrores).toBe(true)
  })

  it('valida filas de comparativa con sus propios campos (renglon/proveedor/precio)', () => {
    const filasComparativa = [{ renglon: '1', proveedor: 'Acme', marca: '', precio: '100.5' }]
    const { result } = renderHook(() => useFilasEditables('comparativa', filasComparativa))
    const filaId = result.current.filas[0]._id
    act(() => result.current.actualizarCelda(filaId, 'proveedor', '   '))
    expect(result.current.erroresPorCelda[`${filaId}:proveedor`]).toBeDefined()
  })

  it('revertirCelda vuelve al valor original y ya no cuenta como modificada', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    const filaId = result.current.filas[0]._id
    act(() => result.current.actualizarCelda(filaId, 'cantidad', '99'))
    expect(result.current.modificadas).toBe(1)
    act(() => result.current.revertirCelda(filaId, 'cantidad'))
    expect(result.current.modificadas).toBe(0)
    expect(result.current.filas[0].cantidad).toBe('10')
  })

  it('una fila borrada no aporta errores aunque tenga campos inválidos', () => {
    const { result } = renderHook(() => useFilasEditables('licitacion', FILAS_LICITACION))
    const filaId = result.current.filas[0]._id
    act(() => result.current.actualizarCelda(filaId, 'cantidad', 'no-numero'))
    expect(result.current.tieneErrores).toBe(true)
    act(() => result.current.borrarFila(filaId))
    expect(result.current.tieneErrores).toBe(false)
  })
})

// Phase 8 (D6/D13.1) — wiring final: orden_compra en CAMPOS_POR_DOCUMENT_TYPE,
// CampoTipo 'decimal-positivo' y parsearPlanEntregas().
const FILAS_ORDEN_COMPRA = [
  {
    numero_renglon: '1',
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad: '100',
    precio_unitario: '1250,00',
    entregas: '50@30|50@60',
    _archivo: 'oc-hospital.pdf',
    _extraction_id: 'ext-1',
  },
  {
    numero_renglon: '',
    descripcion: 'Amoxicilina 500mg x 16',
    cantidad: '80',
    precio_unitario: '980,50',
    entregas: '',
    _archivo: 'oc-hospital.pdf',
    _extraction_id: 'ext-1',
  },
]

describe('useFilasEditables — orden_compra (D6/D13.1, Phase 8)', () => {
  it('trae una entrada orden_compra en CAMPOS_POR_DOCUMENT_TYPE con las columnas de D6', () => {
    const { result } = renderHook(() => useFilasEditables('orden_compra', FILAS_ORDEN_COMPRA))
    const nombresCampo = result.current.campos.map((c) => c.campo)
    expect(nombresCampo).toEqual(
      expect.arrayContaining([
        'numero_renglon',
        'descripcion',
        'cantidad',
        'precio_unitario',
        'entregas',
        '_archivo',
        '_extraction_id',
      ]),
    )
  })

  it('numero_renglon/_archivo/_extraction_id/entregas son columnas de referencia no editables', () => {
    const { result } = renderHook(() => useFilasEditables('orden_compra', FILAS_ORDEN_COMPRA))
    const porCampo = Object.fromEntries(result.current.campos.map((c) => [c.campo, c]))
    expect(porCampo.numero_renglon.editable).toBe(false)
    expect(porCampo._archivo.editable).toBe(false)
    expect(porCampo._extraction_id.editable).toBe(false)
    expect(porCampo.entregas.editable).toBe(false)
    expect(porCampo.descripcion.editable).not.toBe(false)
    expect(porCampo.cantidad.editable).not.toBe(false)
    expect(porCampo.precio_unitario.editable).not.toBe(false)
  })

  it('numero_renglon se renderiza vacío cuando el documento no lo declaró (C10)', () => {
    const { result } = renderHook(() => useFilasEditables('orden_compra', FILAS_ORDEN_COMPRA))
    expect(result.current.filas[1].numero_renglon).toBe('')
  })

  it('las columnas de referencia no editables nunca aportan errores, aunque estén vacías', () => {
    const { result } = renderHook(() => useFilasEditables('orden_compra', FILAS_ORDEN_COMPRA))
    // fila[1] tiene numero_renglon y entregas vacíos -- ninguno de los dos es
    // obligatorio (D6) y ninguno de los dos es editable en la tabla.
    expect(result.current.erroresPorCelda[`${result.current.filas[1]._id}:numero_renglon`]).toBeUndefined()
    expect(result.current.erroresPorCelda[`${result.current.filas[1]._id}:entregas`]).toBeUndefined()
    expect(result.current.tieneErrores).toBe(false)
  })

  it("CampoTipo 'decimal-positivo' valida precio_unitario: vacío, no numérico y <= 0 son inválidos", () => {
    const { result } = renderHook(() => useFilasEditables('orden_compra', FILAS_ORDEN_COMPRA))
    const filaId = result.current.filas[0]._id

    act(() => result.current.actualizarCelda(filaId, 'precio_unitario', ''))
    expect(result.current.erroresPorCelda[`${filaId}:precio_unitario`]).toBeDefined()

    act(() => result.current.actualizarCelda(filaId, 'precio_unitario', 'no-numero'))
    expect(result.current.erroresPorCelda[`${filaId}:precio_unitario`]).toBeDefined()

    act(() => result.current.actualizarCelda(filaId, 'precio_unitario', '0'))
    expect(result.current.erroresPorCelda[`${filaId}:precio_unitario`]).toBeDefined()

    act(() => result.current.actualizarCelda(filaId, 'precio_unitario', '-5'))
    expect(result.current.erroresPorCelda[`${filaId}:precio_unitario`]).toBeDefined()

    act(() => result.current.actualizarCelda(filaId, 'precio_unitario', '1250,50'))
    expect(result.current.erroresPorCelda[`${filaId}:precio_unitario`]).toBeUndefined()
  })
})

describe('parsearPlanEntregas (D6 -- gramática de la columna "entregas")', () => {
  it('parsea "50@30|50@60" en 2 planes con cantidad y plazo_dias', () => {
    expect(parsearPlanEntregas('50@30|50@60')).toEqual([
      { cantidad: '50', plazo_dias: 30 },
      { cantidad: '50', plazo_dias: 60 },
    ])
  })

  it('un único plan sin separador "|" también es válido', () => {
    expect(parsearPlanEntregas('100@0')).toEqual([{ cantidad: '100', plazo_dias: 0 }])
  })

  it('cadena vacía significa "el documento no declara desglose" -- [] sin error', () => {
    expect(parsearPlanEntregas('')).toEqual([])
    expect(parsearPlanEntregas('   ')).toEqual([])
  })

  it.each([
    ['50'], // falta "@plazo_dias"
    ['50@'], // plazo_dias vacío
    ['@30'], // cantidad vacía
    ['abc@30'], // cantidad no numérica
    ['50@-1'], // plazo_dias negativo
    ['50@30.5'], // plazo_dias no entero
    ['50@30|'], // segundo plan vacío tras el separador
  ])('rechaza gramática malformada: %s', (malformado) => {
    expect(parsearPlanEntregas(malformado)).toBeNull()
  })
})
