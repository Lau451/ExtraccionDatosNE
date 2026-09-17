# PCP UI Legacy Import Specification

## Purpose

Provide a dedicated screen to trigger the idempotent legacy PCP bulk import via
`POST /pcp/imports/legacy`, gated to write roles.

## Requirements

### Requirement: Legacy Import Screen Gated by Write Role

The system MUST render a dedicated import screen callable only by write-role users, and MUST NOT
expose the import trigger to a read-only role.

#### Scenario: Write role triggers an import

- GIVEN a write-role user on the legacy import screen
- WHEN they submit the import
- THEN the system calls `POST /pcp/imports/legacy` and shows the resulting summary

#### Scenario: Read-only role cannot access the import screen

- GIVEN a read-only-role user navigates to the legacy import route
- WHEN the route resolves
- THEN the import screen is not rendered and the user is redirected

### Requirement: Import Result Feedback

The system MUST surface the import outcome, including that re-running the same import updates
rather than duplicates PCPs, without requiring the user to inspect raw API output.

#### Scenario: Re-running the same import shows an update, not a duplicate count

- GIVEN a legacy import already created PCPs for a given source file
- WHEN the same source file is imported again
- THEN the screen reports the records as updated existing PCPs, matching the idempotent
  `codigo_legacy` upsert behavior
