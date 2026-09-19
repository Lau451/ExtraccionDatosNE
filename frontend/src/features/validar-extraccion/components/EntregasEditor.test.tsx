import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EntregasEditor, type EntregaPlanEditable, type FilaParaEntregas } from './EntregasEditor'

/** Arnés mínimo (mismo patrón que OrdenCompraSelector/CabeceraOrdenCompra):
 * "Confirmar entregas" se deshabilita según el `bloqueado` que reporta este
 * componente vía `onCambio`. */
function ArnesConBotonConfirmar({ filas }: { filas: FilaParaEntregas[] }) {
  const [bloqueado, setBloqueado] = useState(false)
  const [ultimasEntregas, setUltimasEntregas] = useState<EntregaPlanEditable[]>([])
  return (
    <div>
      <EntregasEditor
        filas={filas}
        onCambio={(entregas, bloqueadoActual) => {
          setUltimasEntregas(entregas)
          setBloqueado(bloqueadoActual)
        }}
      />
      <button type="button" disabled={bloqueado}>
        Confirmar entregas
      </button>
      <p data-testid="cantidad-entregas-reportadas">{ultimasEntregas.length}</p>
    </div>
  )
}

const UN_RENGLON: FilaParaEntregas[] = [{ descripcion: 'Paracetamol 500mg', cantidad: '100' }]

describe('EntregasEditor (D8)', () => {
  it('la suma por renglón que no cuadra deshabilita confirmar, con el mismo mensaje que el espejo del servidor (_validar_orden_compra_override)', () => {
    render(<ArnesConBotonConfirmar filas={UN_RENGLON} />)

    fireEvent.change(screen.getByLabelText(/cantidad de entregas/i), { target: { value: '2' } })
    fireEvent.click(screen.getByLabelText(/desglosar cantidad por línea manualmente/i))

    fireEvent.change(screen.getByLabelText('entrega 1 renglón 1'), { target: { value: '40' } })
    fireEvent.change(screen.getByLabelText('entrega 2 renglón 1'), { target: { value: '40' } })

    expect(
      screen.getByText(
        'renglón 1: la suma de las entregas (80) no coincide con la cantidad del renglón (100)',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /confirmar entregas/i })).toBeDisabled()
  })

  it('reparto automático parejo visible cuando el usuario solo carga cantidad de entregas (sin desglose manual)', () => {
    render(<ArnesConBotonConfirmar filas={UN_RENGLON} />)

    fireEvent.change(screen.getByLabelText(/cantidad de entregas/i), { target: { value: '3' } })

    expect(screen.getByTestId('reparto-automatico')).toHaveTextContent('34 / 33 / 33')
    expect(screen.getByRole('button', { name: /confirmar entregas/i })).not.toBeDisabled()
  })

  it('suma correcta con desglose manual habilita confirmar', () => {
    render(<ArnesConBotonConfirmar filas={UN_RENGLON} />)

    fireEvent.change(screen.getByLabelText(/cantidad de entregas/i), { target: { value: '2' } })
    fireEvent.click(screen.getByLabelText(/desglosar cantidad por línea manualmente/i))

    fireEvent.change(screen.getByLabelText('entrega 1 renglón 1'), { target: { value: '60' } })
    fireEvent.change(screen.getByLabelText('entrega 2 renglón 1'), { target: { value: '40' } })

    expect(screen.getByRole('button', { name: /confirmar entregas/i })).not.toBeDisabled()
    expect(screen.getByTestId('cantidad-entregas-reportadas')).toHaveTextContent('2')
  })
})
