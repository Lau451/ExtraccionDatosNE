import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAutoGrowTextarea } from './useAutoGrowTextarea'

/** T3b: el hook original (T3) solo re-medía en cambios de `value` -- si el
 * ANCHO del textarea cambia (resize de ventana, columna, sidebar) sin que el
 * texto cambie, el alto queda calculado con el ancho viejo y el texto termina
 * clippeado por `overflow-hidden` (el síntoma reportado por el usuario) hasta
 * la próxima edición. Estos tests cubren el ResizeObserver agregado para
 * re-medir también en cambios de ancho. */

function crearTextarea(scrollHeight: number): HTMLTextAreaElement {
  const el = document.createElement('textarea')
  Object.defineProperty(el, 'scrollHeight', { value: scrollHeight, configurable: true })
  return el
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useAutoGrowTextarea', () => {
  it('ajusta la altura al asignar el ref (comportamiento previo, T3)', () => {
    const { result } = renderHook(() => useAutoGrowTextarea('valor'))
    const el = crearTextarea(42)

    result.current.ref(el)

    expect(el.style.height).toBe('42px')
  })

  it('sin ResizeObserver disponible en el entorno (ej. jsdom por default) no rompe', () => {
    // jsdom no implementa ResizeObserver -- este es justamente el entorno de
    // test por default, sin ningún stub global.
    expect('ResizeObserver' in globalThis).toBe(false)

    expect(() => {
      const { result } = renderHook(() => useAutoGrowTextarea('valor'))
      const el = crearTextarea(20)
      result.current.ref(el)
    }).not.toThrow()
  })

  it('con ResizeObserver disponible, observa el elemento asignado por ref', () => {
    const observe = vi.fn()
    const disconnect = vi.fn()
    class FakeResizeObserver {
      constructor(_callback: ResizeObserverCallback) {}
      observe = observe
      disconnect = disconnect
      unobserve = vi.fn()
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const { result } = renderHook(() => useAutoGrowTextarea('valor'))
    const el = crearTextarea(20)
    result.current.ref(el)

    expect(observe).toHaveBeenCalledWith(el)
  })

  it('un cambio de tamaño reportado por ResizeObserver vuelve a medir la altura', () => {
    let callbackRegistrado: ResizeObserverCallback | undefined
    class FakeResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        callbackRegistrado = callback
      }
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const { result } = renderHook(() => useAutoGrowTextarea('valor'))
    const el = crearTextarea(30)
    result.current.ref(el)
    expect(el.style.height).toBe('30px')

    // El texto no cambió, pero el ancho sí (ej. resize de ventana) -- ahora
    // necesita más alto para el mismo contenido.
    Object.defineProperty(el, 'clientWidth', { value: 200, configurable: true })
    Object.defineProperty(el, 'scrollHeight', { value: 90, configurable: true })
    callbackRegistrado?.([] as unknown as ResizeObserverEntry[], {} as ResizeObserver)

    expect(el.style.height).toBe('90px')
  })

  it('una notificación sin cambio de ancho (el propio ajuste de alto) no vuelve a medir', () => {
    let callbackRegistrado: ResizeObserverCallback | undefined
    class FakeResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        callbackRegistrado = callback
      }
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const { result } = renderHook(() => useAutoGrowTextarea('valor'))
    const el = crearTextarea(30)
    result.current.ref(el)

    // Mismo ancho: la notificación viene de nuestro propio cambio de alto.
    Object.defineProperty(el, 'scrollHeight', { value: 90, configurable: true })
    callbackRegistrado?.([] as unknown as ResizeObserverEntry[], {} as ResizeObserver)

    expect(el.style.height).toBe('30px')
  })

  it('desconecta el ResizeObserver al desmontar', () => {
    const disconnect = vi.fn()
    class FakeResizeObserver {
      constructor(_callback: ResizeObserverCallback) {}
      observe = vi.fn()
      disconnect = disconnect
      unobserve = vi.fn()
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const { result, unmount } = renderHook(() => useAutoGrowTextarea('valor'))
    const el = crearTextarea(20)
    result.current.ref(el)

    unmount()

    expect(disconnect).toHaveBeenCalledTimes(1)
  })

  it('al reasignar el ref a otro elemento, desconecta el observer del elemento anterior', () => {
    const disconnect = vi.fn()
    class FakeResizeObserver {
      constructor(_callback: ResizeObserverCallback) {}
      observe = vi.fn()
      disconnect = disconnect
      unobserve = vi.fn()
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const { result } = renderHook(() => useAutoGrowTextarea('valor'))
    const elUno = crearTextarea(20)
    result.current.ref(elUno)

    const elDos = crearTextarea(25)
    result.current.ref(elDos)

    expect(disconnect).toHaveBeenCalledTimes(1)
  })
})
