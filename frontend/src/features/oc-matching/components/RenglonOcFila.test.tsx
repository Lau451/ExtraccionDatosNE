import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { RenglonOrdenCompra } from '@/lib/api/ocMatching'
import { RenglonOcFila } from './RenglonOcFila'

function renglon(overrides: Partial<RenglonOrdenCompra> = {}): RenglonOrdenCompra {
  return {
    oc_item_id: 'item-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad: 10,
    precio_unitario: 1250,
    producto_id: null,
    estado: 'pendiente',
    presupuesto_item_id: null,
    vinculo_origen: null,
    candidatos: [],
    ...overrides,
  }
}

function renderFila(overrides: Partial<RenglonOrdenCompra> = {}, props: Partial<Parameters<typeof RenglonOcFila>[0]> = {}) {
  const onSeleccionar = vi.fn()
  const onConfirmar = vi.fn()
  const onDeshacer = vi.fn()
  const onDescartar = vi.fn()
  render(
    <RenglonOcFila
      renglon={renglon(overrides)}
      seleccionado={false}
      isPending={false}
      onSeleccionar={onSeleccionar}
      onConfirmar={onConfirmar}
      onDeshacer={onDeshacer}
      onDescartar={onDescartar}
      {...props}
    />,
  )
  return { onSeleccionar, onConfirmar, onDeshacer, onDescartar }
}

describe('RenglonOcFila (design.md D4/D13, spec oc-presupuesto-vinculacion)', () => {
  it('un único candidato: "Confirmar" está habilitado y nada viene preseleccionado', () => {
    const { onConfirmar } = renderFila({
      candidatos: [{ presupuesto_item_id: 'pi-1', similitud: null }],
    })

    const boton = screen.getByRole('button', { name: /^confirmar$/i })
    expect(boton).not.toBeDisabled()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()

    fireEvent.click(boton)
    expect(onConfirmar).toHaveBeenCalledWith('pi-1')
  })

  it('varios candidatos: se listan ordenados (orden recibido) y ninguno viene preseleccionado', () => {
    const { onConfirmar } = renderFila({
      candidatos: [
        { presupuesto_item_id: 'pi-1', similitud: 91 },
        { presupuesto_item_id: 'pi-2', similitud: 40 },
      ],
    })

    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(2)
    for (const radio of radios) expect(radio).not.toBeChecked()

    const boton = screen.getByRole('button', { name: /^confirmar$/i })
    expect(boton).toBeDisabled()

    fireEvent.click(radios[1])
    fireEvent.click(boton)
    expect(onConfirmar).toHaveBeenCalledWith('pi-2')
  })

  it('cero candidatos: el estado pendiente queda visible y no bloquea la fila (sigue permitiendo descartar)', () => {
    const { onDescartar } = renderFila({ candidatos: [] })

    expect(screen.getByText('Pendiente')).toBeInTheDocument()
    expect(screen.getByText(/ningún renglón del presupuesto coincide en precio/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^confirmar$/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /no está en el presupuesto/i }))
    expect(onDescartar).toHaveBeenCalled()
  })

  it('confirmado: muestra "Deshacer" y el origen del vínculo, sin ofrecer "Confirmar" de nuevo', () => {
    const { onDeshacer } = renderFila({
      estado: 'confirmado',
      presupuesto_item_id: 'pi-1',
      vinculo_origen: 'precio_exacto',
      candidatos: [],
    })

    expect(screen.getByText(/precio exacto/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^confirmar$/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^deshacer$/i }))
    expect(onDeshacer).toHaveBeenCalled()
  })

  it('sin_presupuesto: muestra el descarte y permite deshacerlo', () => {
    const { onDeshacer } = renderFila({ estado: 'sin_presupuesto', candidatos: [] })

    expect(screen.getByText('No está en el presupuesto')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^deshacer$/i }))
    expect(onDeshacer).toHaveBeenCalled()
  })
})
