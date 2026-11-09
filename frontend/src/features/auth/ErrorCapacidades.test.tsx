import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorCapacidades } from './ErrorCapacidades'

describe('ErrorCapacidades', () => {
  it('muestra el error como alerta y reintenta al tocar el botón', () => {
    const onReintentar = vi.fn()
    render(<ErrorCapacidades mensaje="No se pudieron cargar los permisos de tu usuario (Error interno)." onReintentar={onReintentar} />)

    expect(screen.getByRole('alert').textContent).toBe('No se pudieron cargar los permisos de tu usuario (Error interno).')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onReintentar).toHaveBeenCalledTimes(1)
  })
})
