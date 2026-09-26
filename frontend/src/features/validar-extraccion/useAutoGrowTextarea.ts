import { useCallback, useEffect, useRef } from 'react'

/** Ref callback que ajusta la altura de un `<textarea>` a su contenido (sin
 * scrollbar interno) -- se recalcula en cada cambio de `value` para que
 * pegar/borrar texto largo también actualice el alto (T3), y además cuando
 * cambia el ANCHO del elemento vía `ResizeObserver` (T3b): sin esto, un
 * resize de ventana/columna/sidebar sin tocar el texto dejaba la altura
 * calculada con el ancho viejo, y el texto quedaba clippeado por
 * `overflow-hidden` hasta la próxima edición -- el síntoma reportado por el
 * usuario. `ResizeObserver` no está disponible en todos los entornos (ej.
 * jsdom en tests): se guarda esa ausencia sin romper el resto. Usado por
 * `CeldaEditable` (columna "descripción") y `CabeceraOrdenCompra` (dirección
 * de entrega / observaciones): 3 sitios, de ahí el hook compartido en vez de
 * repetir el cálculo. */
export function useAutoGrowTextarea(value: string) {
  const elRef = useRef<HTMLTextAreaElement | null>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

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
      // Al cambiar de elemento (o desmontar), desconectar el observer anterior
      // antes de crear uno nuevo -- si no, quedaría observando un nodo que ya
      // no es el actual.
      resizeObserverRef.current?.disconnect()
      resizeObserverRef.current = null

      elRef.current = el
      ajustarAltura()

      if (el && typeof ResizeObserver !== 'undefined') {
        // Solo reaccionar a cambios de ANCHO: el propio ajuste de alto también
        // dispara el observer, y re-medir por eso es trabajo inútil (y puede
        // disparar el warning "ResizeObserver loop" del navegador).
        let anchoPrevio = el.clientWidth
        const observer = new ResizeObserver(() => {
          if (el.clientWidth === anchoPrevio) return
          anchoPrevio = el.clientWidth
          ajustarAltura()
        })
        observer.observe(el)
        resizeObserverRef.current = observer
      }
    },
    [ajustarAltura],
  )

  useEffect(() => {
    ajustarAltura()
  }, [value, ajustarAltura])

  useEffect(() => {
    return () => {
      resizeObserverRef.current?.disconnect()
    }
  }, [])

  return { ref, ajustarAltura }
}
