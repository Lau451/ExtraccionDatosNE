# Skill Registry — ExtraccionDatosNE

**Generated**: 2026-05-14
**Project**: ExtraccionDatosNE
**Stack**: Python + FastAPI + Jinja2 + Supabase + Gemini 2.5 Flash
**Persistence**: engram
**Strict TDD Mode**: enabled

## Project Skills (`.claude/skills/`)

### frontend-design
**Triggers**: building web components, pages, HTML/CSS layouts, templates, styling UI
**Path**: `.claude/skills/frontend-design/SKILL.md`
**Compact Rules**:
- Choose BOLD aesthetic direction before coding — commit to it
- NEVER use generic fonts (Inter, Roboto, Arial) or purple gradients
- Use CSS variables; cohesive palette with sharp accents
- Match existing Manrope + dark theme aesthetic of this project

### ui-ux-pro-max
**Triggers**: new pages, UI components (modals, forms, tables), UX reviews, responsive design
**Path**: `.claude/skills/ui-ux-pro-max/SKILL.md`
**Compact Rules**:
- Apply UX guidelines before designing
- Check accessibility on every component
- Stack for this project: HTML/CSS + vanilla JS (Jinja2 templates)

### supabase
**Triggers**: ANY Supabase task — schema, queries, RLS, migrations, supabase-py client
**Path**: `.claude/skills/supabase/SKILL.md`
**Compact Rules**:
- Verify against Supabase changelog before implementing
- Enable RLS on every table in exposed schemas
- NEVER use `user_metadata` for authorization (user-editable)
- Service role key used server-side only (existing pattern)
- Newly created tables may not be auto-exposed to Data API — grant roles explicitly
- After implementing: run a test query to confirm

### supabase-postgres-best-practices
**Triggers**: SQL queries, schema design, indexes, DB performance, connection pooling, RLS
**Path**: `.claude/skills/supabase-postgres-best-practices/SKILL.md`
**Compact Rules**:
- Index all foreign keys and frequently queried columns
- Use partial indexes for filtered queries
- Avoid N+1: use joins or batch selects
- Use UPSERT (ON CONFLICT) for idempotent writes — already used in this project
- Keep transactions short; acquire locks late

## When to Trigger Skills

| Context | Skills |
|---------|--------|
| HTML templates, modals, CSS | frontend-design, ui-ux-pro-max |
| Supabase schema / queries / client | supabase, supabase-postgres-best-practices |
| PR creation | branch-pr |

## Testing Infrastructure

- **Runner**: `pytest tests/` (pytest>=7.0, asyncio_mode=auto)
- **Unit**: ✅ pytest + pytest-mock
- **Integration**: ✅ httpx + FastAPI TestClient
- **E2E**: ❌ not installed
- **Coverage**: ❌ pytest-cov not in requirements.txt
- **Linter / Type checker**: ❌ not configured
