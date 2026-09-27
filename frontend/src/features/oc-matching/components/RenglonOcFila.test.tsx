import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { RenglonOrdenCompra, RenglonPresupuesto } from '@/lib/api/ocMatching'
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

function presupuesto(overrides: Partial<RenglonPresupuesto> = {}): RenglonPresupuesto {
  return {
    presupuesto_item_id: 'pi-1',
    item_proceso_id: 'ip-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad_ofertada: 10,
    precio_unitario: 1250,
    producto_id: null,
    renglones_oc_vinculados: 0,
    renglones_oc_vinculados_otras_oc: 0,
    cantidad_vinculada: 0,
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
      presupuestoPorId={new Map()}
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

  it('varios candidatos: la etiqueta muestra renglón, descripción y precio del presupuesto, nunca el UUID', () => {
    const presupuestoPorId = new Map([
      [
        'pi-1',
        presupuesto({
          presupuesto_item_id: 'pi-1',
          numero_renglon: 3,
          descripcion: 'Ibuprofeno 400mg x 20',
          precio_unitario: 1200,
        }),
      ],
      [
        'pi-2',
        presupuesto({
          presupuesto_item_id: 'pi-2',
          numero_renglon: 7,
          descripcion: 'Paracetamol 500mg x 10',
          precio_unitario: 500,
        }),
      ],
    ])

    renderFila(
      {
        candidatos: [
          { presupuesto_item_id: 'pi-1', similitud: 91 },
          { presupuesto_item_id: 'pi-2', similitud: null },
        ],
      },
      { presupuestoPorId },
    )

    expect(
      screen.getByText('Renglón 3 — Ibuprofeno 400mg x 20 — $1200 — 91% similitud'),
    ).toBeInTheDocument()
    expect(screen.getByText('Renglón 7 — Paracetamol 500mg x 10 — $500')).toBeInTheDocument()
    expect(screen.queryByText('pi-1')).not.toBeInTheDocument()
    expect(screen.queryByText('pi-2')).not.toBeInTheDocument()
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
