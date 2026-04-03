# Skill Registry

**Generated**: 2026-04-02
**Project**: ExtraccionDatosNE
**Stack**: Python 3.9+, FastAPI, Pandas, Google Generative AI

## Global Skills (User-level)

### SDD Workflow Skills
- **sdd-apply** (v3.0): Implement tasks from change specs
- **sdd-archive** (v?): Archive completed changes
- **sdd-design** (v?): Create technical design documents
- **sdd-explore** (v?): Investigate and explore ideas
- **sdd-init** (v?): Initialize SDD context in project
- **sdd-onboard** (v?): Guided SDD workflow walkthrough
- **sdd-propose** (v?): Create change proposals
- **sdd-spec** (v?): Write specifications with scenarios
- **sdd-tasks** (v?): Break down changes into task checklists
- **sdd-verify** (v?): Validate implementation against specs

### Integration Skills
- **branch-pr** (v2.0): PR creation workflow for Agent Teams Lite
- **issue-creation** (v?): Issue creation workflow for Agent Teams Lite
- **judgment-day** (v?): Parallel adversarial review protocol

### Quality & Testing Skills
- **go-testing** (v?): Go testing patterns including Bubbletea TUI testing
- **skill-creator** (v?): Create new AI agent skills

### Shared Utilities
- **_shared**: Common conventions and patterns

---

## Project Skills (.agents/skills)

### UI/Design Skills
- **frontend-design**: Create distinctive, production-grade frontend interfaces with high design quality
  - Use when building web components, pages, dashboards, React components, or styling web UI
  - Trigger: User asks to build web components, pages, applications, posters, or interfaces

- **ui-ux-pro-max**: Professional UI/UX design patterns and implementations
  - Specialized UX design for this project

---

## Compact Rules (Auto-resolved on delegation)

### Project Conventions
- **Python style**: Follow PEP 8 conventions
- **API design**: FastAPI patterns for endpoints
- **Error handling**: Google Generative AI API error handling
- **File I/O**: Use pathlib for cross-platform paths
- **Logging**: Standard Python logging module
- **Testing**: Integration with Google Sheets/Excel data

### When to Trigger Skills
| Context | Skill | Trigger |
|---------|-------|---------|
| Frontend/Web UI work | frontend-design, ui-ux-pro-max | Building templates, static assets, web components |
| Change management | sdd-* | SDD workflow (proposal, spec, design, tasks, apply, verify) |
| PR creation | branch-pr | Creating pull requests or preparing branch for review |
| Issue tracking | issue-creation | Creating GitHub issues, reporting bugs, requesting features |
| Code review | judgment-day | Parallel adversarial review ("judgment day", "doble review") |

---

## Testing Infrastructure Status

See `sdd-init/{project-name}/testing-capabilities` in engram for current test capability matrix.

**Current State**: No test framework installed (pytest not in requirements.txt)

To enable Strict TDD Mode:
1. Add `pytest` and `pytest-cov` to requirements.txt
2. Re-run `/sdd-init` to update testing capabilities
