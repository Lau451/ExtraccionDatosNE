import { describe, expect, it } from 'vitest'
import { etiquetaRenglonOc } from './etiquetaRenglonOc'

describe('etiquetaRenglonOc (spec oc-numero-renglon-documento)', () => {
  it('usa el número impreso en el documento cuando existe', () => {
    expect(etiquetaRenglonOc({ numero_renglon: 4, numero_renglon_documento: '38' })).toBe('38')
  })

  it('cae al número posicional (D13.1) cuando el documento no lo tiene', () => {
    expect(etiquetaRenglonOc({ numero_renglon: 4, numero_renglon_documento: null })).toBe('4')
  })
})
