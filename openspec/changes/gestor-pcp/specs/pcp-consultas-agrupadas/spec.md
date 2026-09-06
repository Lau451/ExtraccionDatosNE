# PCP Consultas Agrupadas Specification

## Purpose

Let Compras group several products destined for the same supplier — within one PCP or across several
open PCPs — into a single supplier consulta, generate one PDF for it, and deliver it to the supplier's
contact through the channel(s) configured for outbound delivery.

## Requirements

### Requirement: Cross-PCP Grouping by Supplier

The system MUST allow grouping renglones for the same proveedor, drawn from one PCP or from multiple
open PCPs, into a single consulta.

#### Scenario: Group renglones from a single PCP

- GIVEN a PCP with three renglones assigned to the same proveedor P
- WHEN Compras groups those renglones into one consulta
- THEN the system creates one consulta containing all three renglones for P

#### Scenario: Group renglones across multiple PCPs

- GIVEN two open PCPs each have a renglón assigned to proveedor P
- WHEN Compras groups both renglones into one consulta
- THEN the system creates one consulta referencing renglones from both PCPs
- AND each renglón still traces back to its own originating PCP

### Requirement: Consulta PDF Generation

The system MUST generate one PDF document per consulta, listing every grouped renglón intended for
that proveedor.

#### Scenario: Generate a PDF for a grouped consulta

- GIVEN a consulta grouping three renglones for proveedor P
- WHEN the consulta's PDF is generated
- THEN the PDF lists all three renglones
- AND identifies proveedor P as the recipient

### Requirement: Outbound Delivery via Configured Channel(s)

The system MUST deliver a consulta's PDF to the proveedor's contact using the channel(s) configured
for outbound delivery, sourcing contact data from the existing terceros contact records, and MUST NOT
hardcode a specific messaging vendor into this requirement.

#### Scenario: Deliver a consulta through a configured channel

- GIVEN proveedor P has a contact record with delivery-capable contact data
- AND at least one outbound channel is configured and enabled
- WHEN the consulta for P is sent
- THEN the system delivers the consulta PDF to P's contact through every enabled configured channel

#### Scenario: Reject sending without a usable contact

- GIVEN proveedor P has no contact record with delivery-capable contact data
- WHEN Compras attempts to send a consulta to P
- THEN the system rejects the send
- AND no delivery attempt is made

#### Scenario: Delivery failure does not corrupt grouping

- GIVEN a consulta was generated and grouped correctly
- WHEN the outbound delivery attempt fails
- THEN the consulta and its renglón grouping remain intact for a retry
- AND no renglón is silently dropped from the group
