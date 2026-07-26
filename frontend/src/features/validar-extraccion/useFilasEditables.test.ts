import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useFilasEditables } from './useFilasEditables'

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
