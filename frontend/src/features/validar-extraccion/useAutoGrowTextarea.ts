import { useCallback, useEffect, useRef } from 'react'

/** Ref callback que ajusta la altura de un `<textarea>` a su contenido (sin
 * scrollbar interno) -- se recalcula en cada cambio de `value` para que
 * pegar/borrar texto largo también actualice el alto (T3). Usado por
 * `CeldaEditable` (columna "descripción") y `CabeceraOrdenCompra` (dirección
 * de entrega / observaciones): 3 sitios, de ahí el hook compartido en vez de
 * repetir el cálculo. */
export function useAutoGrowTextarea(value: string) {
  const elRef = useRef<HTMLTextAreaElement | null>(null)

  const ajustarAltura = useCallback(() => {
    const el = elRef.current
    if (!el) return
    // Resetear a 'auto' antes de medir -- si no, `scrollHeight` solo podría
    // crecer y nunca encogerse cuando se borra texto.
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [])

  // Callback ref (no un objeto mutable expuesto) -- así el consumidor puede
  // componerlo con su propio ref sin mutar un valor devuelto por el hook.
  const ref = useCallback(
    (el: HTMLTextAreaElement | null) => {
      elRef.current = el
      ajustarAltura()
    },
    [ajustarAltura],
  )

  useEffect(() => {
    ajustarAltura()
  }, [value, ajustarAltura])

  return { ref, ajustarAltura }
}
