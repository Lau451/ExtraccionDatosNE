# PCP UI Consultas Specification

## Purpose

Let write-role users group selected renglones by supplier into one or more consultations in a
single submission, view a consultation's detail, download its PDF, and trigger send, backed by the
`consultas` router.

## Requirements

### Requirement: Group Renglones into Consultations Gated by Write Role

The system MUST let a write-role user select renglones across one or more open PCPs assigned to
the same proveedor and group them into a consultation in a single `POST /pcp/consultas` call, and
MUST NOT render the grouping action for a read-only role.

#### Scenario: Group renglones from a single PCP

- GIVEN three renglones on one PCP assigned to the same proveedor
- WHEN the write-role user selects all three and confirms grouping
- THEN the system creates one consultation containing all three renglones

#### Scenario: Read-only role cannot group

- GIVEN a read-only-role user views renglones eligible for grouping
- WHEN the screen renders
- THEN no grouping action is shown

### Requirement: Consultation Detail and PDF Download

The system MUST show a consultation's detail (grouped renglones, proveedor) and MUST let every
read-role user download its PDF via `GET /pcp/consultas/{id}/pdf` as a binary file.

#### Scenario: Download the consultation PDF

- GIVEN an existing consultation
- WHEN the user triggers "Download PDF"
- THEN the system fetches the binary response and saves/opens it as a PDF file

### Requirement: Send Consultation Action Gated by Write Role

The system MUST render an "Enviar consulta" action for write-role users that calls the
consultation's send endpoint and reflects a success or failure state; it MUST NOT surface any
messaging-adapter-specific detail in the UI and MUST NOT render the send action for a read-only
role.

#### Scenario: Trigger send from the detail view

- GIVEN a grouped consultation ready to send
- WHEN the write-role user triggers "Enviar consulta"
- THEN the system calls the send endpoint and shows a success confirmation on a successful
  response

#### Scenario: Read-only role cannot send

- GIVEN a read-only-role user views a consultation detail
- WHEN the screen renders
- THEN no "Enviar consulta" action is shown
