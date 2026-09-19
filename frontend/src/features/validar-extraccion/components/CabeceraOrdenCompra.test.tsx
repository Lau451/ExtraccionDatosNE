import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CabeceraOrdenCompra } from './CabeceraOrdenCompra'

/** Arnés mínimo (mismo patrón que OrdenCompraSelector.test.tsx): el botón
 * "Confirmar OC" real (Phase 8) se deshabilita según el `bloqueado` que
 * reporta este componente vía `onCambio` -- acá se reproduce sin necesitar
 * el wiring completo. */
function ArnesConBotonConfirmar({ filas }: { filas: Record<string, string>[] }) {
  const [bloqueado, setBloqueado] = useState(true)
  return (
    <div>
      <CabeceraOrdenCompra filas={filas} onCambio={(_cabecera, bloqueadoActual) => setBloqueado(bloqueadoActual)} />
      <button type="button" disabled={bloqueado}>
        Confirmar OC
      </button>
    </div>
  )
}

const MIEMBRO_A = {
  _extraction_id: 'ext-a',
  numero_oc: '1001',
  razon_social_cliente: 'Hospital Central',
  cuit_cliente: '30-11111111-1',
  fecha_emision: '2026-01-10',
  direccion_entrega: 'Calle Falsa 123',
  cantidad_entregas: '2',
}

const MIEMBRO_B_NUMERO_OC_DISTINTO = {
  ...MIEMBRO_A,
  _extraction_id: 'ext-b',
  numero_oc: '1002',
}

const MIEMBRO_B_OTROS_CAMPOS_DISTINTOS = {
  ...MIEMBRO_A,
  _extraction_id: 'ext-b',
  razon_social_cliente: 'Hospital Central S.A.',
  fecha_emision: '2026-01-15',
  direccion_entrega: 'Otra Dirección 456',
}

describe('CabeceraOrdenCompra (D13.1)', () => {
  it('numero_oc en desacuerdo entre miembros: campo en rojo y "Confirmar OC" deshabilitado', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, MIEMBRO_B_NUMERO_OC_DISTINTO]} />)

    const input = screen.getByLabelText(/número de oc/i)
    expect(input).toHaveClass('border-red-500')
    expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled()
  })

  it('editar numero_oc a un valor único habilita "Confirmar OC"', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, MIEMBRO_B_NUMERO_OC_DISTINTO]} />)

    expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled()

    // Distinto de los dos valores declarados ("1001"/"1002") Y del valor que
    // ya muestra el input por empate (D13.1 -- primer miembro gana), para no
    // pisar el "gotcha" de React con inputs controlados: si `fireEvent.change`
    // manda el mismo valor que ya tiene el nodo, React no dispara `onChange`.
    fireEvent.change(screen.getByLabelText(/número de oc/i), { target: { value: '9999' } })

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
  })

  it('desacuerdo en razón social / fecha de emisión / dirección de entrega muestra aviso pero no bloquea', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, MIEMBRO_B_OTROS_CAMPOS_DISTINTOS]} />)

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
    const aviso = screen.getByText(/desacuerdo entre archivos del grupo/i)
    expect(aviso).toHaveTextContent(/razón social/i)
    expect(aviso).toHaveTextContent(/fecha de emisión/i)
    expect(aviso).toHaveTextContent(/dirección de entrega/i)
  })

  it('sin desacuerdo entre miembros: sin aviso y "Confirmar OC" habilitado de entrada', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, { ...MIEMBRO_A, _extraction_id: 'ext-b' }]} />)

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
    expect(screen.queryByText(/desacuerdo/i)).not.toBeInTheDocument()
  })
})
