-- =============================================================================
-- EXTRACTOR IA — DDL v15
-- =============================================================================
-- Cambios de la revisión completa:
--   - procesos_comerciales reemplaza a licitaciones, con clase:
--       cotizacion  → entrega inmediata, sin seguimiento, el motor VALIDA stock
--       licitacion  → con seguimiento completo, el motor NO valida stock
--   - Separación extracción/negocio: extraction_results guarda lo documental
--     (archivo, sha256, status). Las tablas de negocio (comparativas, OC) se
--     crean recién al validar la extracción y solo llevan datos de negocio.
--   - droguerias: + provincia, codigo_postal
--   - clientes: + ciudad, provincia, codigo_postal, plazo_pago_dias,
--     condiciones_pago. Tabla nueva cliente_contactos (múltiples contactos).
--   - categorias: tabla normalizada (medicamentos, descartables, etc.)
--     usada por productos, reglas_pricing y procesos.
--   - productos: campos de medicamento opcionales (descartables no los usan)
--   - items_proceso (ex items_licitacion): sin unidad_medida
--   - oc_items: + producto_id (trazabilidad producto→entrega)
--   - compras_proveedor: NUEVA — a quién le compraste realmente al ganar
--   - Todo en pesos (sin multi-moneda)
--   - Se mantienen: historial de costos con vigencia, multi-depósito,
--     precios_proveedor con mantenimiento, versionado de comparativas y OC,
--     adjudicacion_estimada vs adjudicada, CRM, formato para prompt
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- =============================================================================
-- CAPA 1 — IDENTIDAD Y CRM
-- =============================================================================

CREATE TABLE droguerias (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    nombre              TEXT            NOT NULL,
    razon_social        TEXT            NOT NULL,
    cuit                TEXT            NOT NULL,
    ciudad              TEXT            NOT NULL,
    provincia           TEXT            NOT NULL,
    codigo_postal       TEXT            NULL,
    contacto_email      TEXT            NOT NULL,
    contacto_telefono   TEXT            NOT NULL,
    activa              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_droguerias_cuit UNIQUE (cuit)
);

CREATE TABLE clientes (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    nombre              TEXT            NOT NULL,
    tipo                TEXT            NOT NULL,
    direccion           TEXT            NULL,
    ciudad              TEXT            NULL,
    provincia           TEXT            NULL,
    codigo_postal       TEXT            NULL,
    -- condiciones comerciales del cliente (cómo NOS paga)
    plazo_pago_dias     INTEGER         NULL,
    condiciones_pago    TEXT            NULL,
    activo              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_cli_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_clientes_tipo
        CHECK (tipo IN ('hospital', 'obra_social', 'municipio', 'provincia', 'nacional', 'otro')),
    CONSTRAINT ck_clientes_plazo CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0)
);

COMMENT ON COLUMN clientes.plazo_pago_dias  IS 'A cuántos días paga este cliente (30/60/90). Informativo para evaluar la conveniencia de una licitación.';
COMMENT ON COLUMN clientes.condiciones_pago IS 'Notas libres: "50% contra entrega", "paga con demora habitual", etc.';

-- Múltiples contactos por organismo (compras, farmacia, tesorería…)
CREATE TABLE cliente_contactos (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    cliente_id      UUID            NOT NULL,
    drogueria_id    UUID            NOT NULL,
    nombre          TEXT            NOT NULL,
    cargo           TEXT            NULL,
    email           TEXT            NULL,
    telefono        TEXT            NULL,
    es_principal    BOOLEAN         NOT NULL DEFAULT FALSE,
    notas           TEXT            NULL,
    activo          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

COMMENT ON COLUMN cliente_contactos.drogueria_id IS 'Denormalizado del cliente padre vía FK compuesta (cliente_id, drogueria_id) → clientes(id, drogueria_id). Evita JOIN en cada política RLS.';

-- CRM: bitácora de notas. Se acumulan, no se editan.
CREATE TABLE cliente_observaciones (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    cliente_id          UUID            NOT NULL,
    drogueria_id        UUID            NOT NULL,
    categoria           TEXT            NOT NULL DEFAULT 'general',
    observacion         TEXT            NOT NULL,
    creado_por          UUID            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_cobs_categoria
        CHECK (categoria IN ('general', 'pago', 'contacto', 'logistica', 'historial', 'alerta', 'otro'))
);

-- Perfil de formato por cliente y tipo de documento (se inyecta al prompt del LLM)
CREATE TABLE cliente_formato_documentos (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    cliente_id              UUID            NOT NULL,
    drogueria_id            UUID            NOT NULL,
    doc_type                TEXT            NOT NULL,
    descripcion_estructura  TEXT            NULL,
    instrucciones_prompt    TEXT            NULL,
    archivo_ejemplo_path    TEXT            NULL,
    archivo_ejemplo_nombre  TEXT            NULL,
    activo                  BOOLEAN         NOT NULL DEFAULT TRUE,
    actualizado_por         UUID            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_cliente_formato UNIQUE (cliente_id, doc_type),
    CONSTRAINT ck_cfmt_doc_type
        CHECK (doc_type IN ('comparativa', 'licitacion', 'cotizacion', 'orden_compra'))
);

-- Proveedores: competidores en comparativas y/o proveedores de compra
CREATE TABLE proveedores (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    codigo_interno      TEXT            NULL,
    razon_social        TEXT            NOT NULL,
    nombre_comercial    TEXT            NULL,
    cuit                TEXT            NULL,
    tipo                TEXT            NOT NULL DEFAULT 'otro',
    es_competidor       BOOLEAN         NOT NULL DEFAULT TRUE,
    es_proveedor_compra BOOLEAN         NOT NULL DEFAULT FALSE,
    plazo_pago_dias     INTEGER         NULL,
    condiciones_pago    TEXT            NULL,
    activo              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_prov_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_prov_tipo
        CHECK (tipo IN ('laboratorio', 'drogueria', 'distribuidor', 'cooperativa', 'otro')),
    CONSTRAINT ck_prov_plazo CHECK (plazo_pago_dias IS NULL OR plazo_pago_dias >= 0)
);

COMMENT ON COLUMN proveedores.codigo_interno   IS 'Código del sistema externo de la droguería. Distinto del id (clave interna de esta BD): permite el import idempotente.';
COMMENT ON COLUMN proveedores.plazo_pago_dias  IS 'A cuántos días LE PAGAMOS a este proveedor (30/60/90). Informativo para el aprobador.';


-- =============================================================================
-- CAPA 2 — CATÁLOGO
-- =============================================================================

-- Categorías normalizadas: medicamentos, descartables, soluciones, pañales…
-- Usadas por productos, reglas_pricing y procesos_comerciales.
CREATE TABLE categorias (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID            NOT NULL,
    nombre          TEXT            NOT NULL,
    descripcion     TEXT            NULL,
    activa          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_categorias UNIQUE (drogueria_id, nombre)
);

COMMENT ON TABLE categorias IS 'Rubros normalizados (medicamentos, descartables, soluciones, pañales, fórmulas…). Evita texto libre inconsistente en productos, reglas y procesos.';

-- Catálogo de productos. Los campos de medicamento son opcionales:
-- un descartable (jeringa, guantes) simplemente no los completa.
CREATE TABLE productos (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    codigo_interno      TEXT            NOT NULL,
    nombre              TEXT            NOT NULL,
    categoria_id        UUID            NULL,
    clasificacion       TEXT            NULL,
    -- específicos de medicamentos (NULL para descartables y otros rubros)
    droga               TEXT            NULL,
    presentacion        TEXT            NULL,
    forma_farmaceutica  TEXT            NULL,
    laboratorio         TEXT            NULL,
    codigo_anmat        TEXT            NULL,
    activo              BOOLEAN         NOT NULL DEFAULT TRUE,
    datos_sistema       JSONB           NULL,
    -- auditoría + soft delete
    created_by          UUID            NULL,
    updated_by          UUID            NULL,
    deleted_at          TIMESTAMPTZ     NULL,
    deleted_by          UUID            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_productos UNIQUE (drogueria_id, codigo_interno),
    CONSTRAINT ck_productos_clasificacion CHECK (
        clasificacion IS NULL OR clasificacion IN (
            'medicamento', 'descartable', 'insumo', 'equipamiento', 'perfumeria', 'otro'
        )
    )
);

COMMENT ON COLUMN productos.categoria_id IS 'FK a categorias. Clasifica el producto (medicamentos, descartables…) para reglas de pricing y análisis.';
COMMENT ON COLUMN productos.clasificacion IS 'Clasificación del sistema (enum fijo), distinta de categoria_id que es libre por droguería. Facilita reglas transversales y reportes.';

-- Historial de costos con vigencia.
-- fecha_hasta NO es predicción: se completa automáticamente cuando entra el
-- costo siguiente. El vigente siempre tiene fecha_hasta = NULL.
CREATE TABLE costos_productos (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    producto_id         UUID            NOT NULL,
    drogueria_id        UUID            NOT NULL,
    costo_unitario      NUMERIC(15, 2)  NOT NULL,
    fecha_desde         DATE            NOT NULL,
    fecha_hasta         DATE            NULL,
    origen              TEXT            NOT NULL DEFAULT 'import_sistema',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_costos_vigencia CHECK (fecha_hasta IS NULL OR fecha_hasta >= fecha_desde),
    CONSTRAINT ck_costos_origen CHECK (origen IN ('import_sistema', 'manual')),
    CONSTRAINT ck_costos_valor CHECK (costo_unitario >= 0)
);

COMMENT ON COLUMN costos_productos.fecha_hasta IS 'NULL = costo vigente. Al importar un costo nuevo, la app cierra el anterior (fecha_hasta = fecha_desde nueva - 1). Sirve para que los reportes históricos usen el costo correcto de cada época.';
COMMENT ON COLUMN costos_productos.origen      IS 'import_sistema: vino del export del sistema de la droguería. manual: lo cargó una persona.';

-- Stock por depósito, sincronizado desde el sistema interno.
CREATE TABLE stock_productos (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    producto_id             UUID            NOT NULL,
    drogueria_id            UUID            NOT NULL,
    deposito                TEXT            NULL,
    cantidad_disponible     NUMERIC(12, 2)  NOT NULL DEFAULT 0,
    cantidad_comprometida   NUMERIC(12, 2)  NOT NULL DEFAULT 0,
    fecha_actualizacion     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_stock UNIQUE (producto_id, deposito),
    CONSTRAINT ck_stock_cant CHECK (cantidad_disponible >= 0 AND cantidad_comprometida >= 0)
);

COMMENT ON COLUMN stock_productos.deposito              IS 'En qué depósito físico está la mercadería. La droguería maneja varios.';
COMMENT ON COLUMN stock_productos.cantidad_comprometida IS 'Mantenida por la APP (no viene del sistema): al presentar un presupuesto se suma lo ofertado; al entregar o perder, se resta. Actualizar siempre con UPDATE ... SET x = x + N (atómico).';

-- Memoria de matching descripción→producto por cliente.
CREATE TABLE cliente_producto_alias (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    cliente_id                  UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    producto_id                 UUID            NOT NULL,
    descripcion_original        TEXT            NOT NULL,
    descripcion_normalizada     TEXT            NOT NULL,
    veces_usado                 INTEGER         NOT NULL DEFAULT 1,
    ultimo_uso_at               TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    vigente                     BOOLEAN         NOT NULL DEFAULT TRUE,
    creado_por                  UUID            NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_alias_vigente
    ON cliente_producto_alias (cliente_id, descripcion_normalizada)
    WHERE vigente = TRUE;

COMMENT ON TABLE cliente_producto_alias IS 'Cuando un humano confirma que "IBUPROFENO 600MG X30" del Hospital X es el producto MED-483, queda acá. La próxima vez que ese cliente use esa descripción, el matching es automático. El sistema aprende el vocabulario de cada cliente.';

-- Precios especiales de proveedores de compra, con mantenimiento de oferta.
CREATE TABLE precios_proveedor (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    proveedor_id        UUID            NOT NULL,
    producto_id         UUID            NOT NULL,
    item_proceso_id     UUID            NULL,
    precio_unitario     NUMERIC(15, 2)  NOT NULL,
    cantidad_minima     NUMERIC(12, 2)  NULL,
    cantidad_maxima     NUMERIC(12, 2)  NULL,
    plazo_pago_dias     INTEGER         NULL,
    fecha_oferta        DATE            NOT NULL DEFAULT CURRENT_DATE,
    mantenimiento_hasta DATE            NOT NULL,
    activa              BOOLEAN         NOT NULL DEFAULT TRUE,
    notas               TEXT            NULL,
    creado_por          UUID            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_pp_precio CHECK (precio_unitario >= 0),
    CONSTRAINT ck_pp_mant CHECK (mantenimiento_hasta >= fecha_oferta)
);

COMMENT ON TABLE precios_proveedor IS 'Precios especiales cotizados por proveedores. Vigente = activa AND mantenimiento_hasta >= hoy. item_proceso_id NOT NULL = precio puntual para ese renglón; NULL = precio general del producto. El motor lo usa como costo si es más barato que el estándar.';
COMMENT ON COLUMN precios_proveedor.mantenimiento_hasta IS 'Hasta cuándo el proveedor mantiene el precio. Si vence antes que el vencimiento del proceso, el aprobador ve la alerta.';


-- =============================================================================
-- CAPA 3 — PROCESOS COMERCIALES (cotizaciones + licitaciones)
-- =============================================================================

CREATE TABLE procesos_comerciales (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    cliente_id          UUID            NULL,
    clase               TEXT            NOT NULL,
    nombre              TEXT            NOT NULL,
    categoria_id        UUID            NULL,
    fecha               DATE            NOT NULL DEFAULT CURRENT_DATE,
    estado              TEXT            NOT NULL DEFAULT 'abierto',
    monto_estimado      NUMERIC(15, 2)  NULL,
    notas               TEXT            NULL,
    -- seguimiento (solo clase = 'licitacion'; NULL/FALSE en cotizaciones)
    apertura            DATE            NULL,
    vencimiento         DATE            NULL,
    tipo_gestion        TEXT            NULL,
    modalidad           TEXT            NULL,
    comparativa_pedida  BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_proc_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_proc_clase CHECK (clase IN ('cotizacion', 'licitacion')),
    CONSTRAINT ck_proc_estado CHECK (estado IN (
        'abierto', 'presupuestado', 'presentado',
        'en_evaluacion', 'adjudicado', 'perdido', 'cerrado', 'cancelado'
    )),
    CONSTRAINT ck_proc_modalidad CHECK (modalidad IS NULL OR modalidad IN ('mail', 'pliego')),
    CONSTRAINT ck_proc_cotizacion_sin_seguimiento CHECK (
        clase = 'licitacion' OR
        (apertura IS NULL AND vencimiento IS NULL AND tipo_gestion IS NULL
         AND modalidad IS NULL AND comparativa_pedida = FALSE)
    )
);

COMMENT ON COLUMN procesos_comerciales.clase IS 'DETERMINA EL FLUJO: cotizacion = entrega inmediata, rápida, sin seguimiento, el motor VALIDA STOCK. licitacion = con seguimiento completo (apertura, vencimiento, comparativa), el motor NO valida stock porque hay plazo de entrega.';
COMMENT ON COLUMN procesos_comerciales.apertura IS 'Solo licitaciones. NULL en cotizaciones.';
COMMENT ON COLUMN procesos_comerciales.comparativa_pedida IS 'Se pidió la comparativa al organismo y todavía no llegó. Que YA esté cargada se deriva de la existencia de una fila en comparativas (es_vigente=TRUE) — no se guarda acá, es información derivable.';


-- =============================================================================
-- CAPA 4 — EXTRACCIÓN (documental, separada del negocio)
-- =============================================================================
-- La extracción es el dato CRUDO que el programa saca del documento.
-- Las tablas de negocio (comparativas, ordenes_compra) se crean recién
-- cuando la extracción se valida. Acá queda todo lo documental:
-- archivo, hash, estado del procesamiento.
-- =============================================================================

CREATE TABLE processing_sessions (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    proceso_comercial_id    UUID            NULL,
    doc_name                TEXT            NOT NULL,
    doc_type                TEXT            NOT NULL,
    total_chunks            INTEGER         NOT NULL DEFAULT 0,
    status                  TEXT            NOT NULL DEFAULT 'running',
    error_msg               TEXT            NULL,
    formato_usado_id        UUID            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ     NULL,
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_ps_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_ps_doc_type CHECK (doc_type IN ('comparativa', 'licitacion', 'cotizacion', 'orden_compra')),
    CONSTRAINT ck_ps_status CHECK (status IN ('running', 'completed', 'partial', 'failed'))
);

CREATE TABLE extraction_results (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    session_id              UUID            NULL,
    drogueria_id            UUID            NOT NULL,
    proceso_comercial_id    UUID            NULL,
    document_type           TEXT            NOT NULL,
    source_filename         TEXT            NOT NULL,
    source_sha256           TEXT            NOT NULL,
    row_count               INTEGER         NOT NULL DEFAULT 0,
    csv_disk_path           TEXT            NULL,
    archivo_path            TEXT            NULL,
    status                  TEXT            NOT NULL DEFAULT 'completed',
    validado                BOOLEAN         NOT NULL DEFAULT FALSE,
    validado_por            UUID            NULL,
    validado_at             TIMESTAMPTZ     NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_er_sha256 UNIQUE (source_sha256),
    CONSTRAINT ck_er_doc_type CHECK (document_type IN ('comparativa', 'licitacion', 'cotizacion', 'orden_compra')),
    CONSTRAINT ck_er_status CHECK (status IN ('completed', 'partial', 'failed'))
);

COMMENT ON COLUMN extraction_results.validado IS 'FALSE = extracción cruda sin revisar. TRUE = un humano validó y los datos se materializaron en las tablas de negocio (items_proceso / comparativas / ordenes_compra).';
COMMENT ON COLUMN extraction_results.archivo_path IS 'El documento original. Los datos documentales viven acá, NO en las tablas de negocio.';

CREATE TABLE chunk_results (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    session_id      UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    chunk_number    INTEGER         NOT NULL,
    resultado       JSONB           NOT NULL,
    status          TEXT            NOT NULL DEFAULT 'completed',
    attempts        INTEGER         NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_chunk UNIQUE (session_id, chunk_number),
    CONSTRAINT ck_chunk_status CHECK (status IN ('completed', 'failed'))
);


-- =============================================================================
-- CAPA 5 — RENGLONES Y MATCHING
-- =============================================================================

CREATE TABLE items_proceso (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    proceso_comercial_id    UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    extraction_id           UUID            NULL,
    numero_renglon          INTEGER         NOT NULL,
    descripcion             TEXT            NOT NULL,
    descripcion_normalizada TEXT            NULL,
    cantidad                NUMERIC(12, 2)  NOT NULL,
    monto_estimado          NUMERIC(15, 2)  NULL,
    -- matching contra catálogo
    producto_id             UUID            NULL,
    alias_id                UUID            NULL,
    estado_matching         TEXT            NOT NULL DEFAULT 'pendiente',
    confianza_matching      NUMERIC(5, 2)   NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_ip_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_items_proceso UNIQUE (proceso_comercial_id, numero_renglon),
    CONSTRAINT ck_ip_matching
        CHECK (estado_matching IN ('pendiente', 'automatico', 'sugerido', 'confirmado', 'sin_match'))
);

COMMENT ON COLUMN items_proceso.monto_estimado   IS 'Precio referencial del organismo por renglón (cuando el pliego lo publica). Sirve para validar que la oferta esté en rango. NULL si no viene.';
COMMENT ON COLUMN items_proceso.alias_id         IS 'Si el matching se resolvió por un alias existente, cuál. Trazabilidad de por qué se matcheó automáticamente.';
COMMENT ON COLUMN items_proceso.estado_matching  IS 'pendiente → automatico (alias lo resolvió solo) / sugerido (IA propone, falta confirmar) → confirmado / sin_match (no vendemos ese producto).';

-- Top-K de productos candidatos cuando no hay alias. El humano elige uno
-- → se matchea el renglón Y se crea el alias para el futuro.
CREATE TABLE matching_candidatos (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    item_proceso_id     UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    producto_id         UUID            NOT NULL,
    confianza           NUMERIC(5, 2)   NOT NULL,
    metodo              TEXT            NOT NULL,
    detalle_scoring     JSONB           NULL,
    elegido             BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_mc UNIQUE (item_proceso_id, producto_id),
    CONSTRAINT ck_mc_conf CHECK (confianza >= 0 AND confianza <= 100),
    CONSTRAINT ck_mc_metodo CHECK (metodo IN ('exact', 'fuzzy', 'embedding', 'manual'))
);


-- =============================================================================
-- CAPA 6 — MOTOR DE PRICING Y PRESUPUESTO AUTOMÁTICO
-- =============================================================================

CREATE TABLE reglas_pricing (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id                UUID            NOT NULL,
    nombre                      TEXT            NOT NULL,
    -- alcance (NULL = aplica a todo)
    cliente_id                  UUID            NULL,
    clase_proceso               TEXT            NULL,
    categoria_id                UUID            NULL,
    -- estrategia combinada: mercado como referencia, margen mínimo como piso
    margen_minimo_pct           NUMERIC(7, 2)   NOT NULL,
    descuento_vs_mercado_pct    NUMERIC(5, 2)   NULL,
    margen_objetivo_pct         NUMERIC(7, 2)   NULL,
    meses_ventana_mercado       INTEGER         NOT NULL DEFAULT 6,
    prioridad                   INTEGER         NOT NULL DEFAULT 0,
    activa                      BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_rp_clase CHECK (clase_proceso IS NULL OR clase_proceso IN ('cotizacion', 'licitacion')),
    CONSTRAINT ck_rp_margen CHECK (margen_minimo_pct >= 0)
);

COMMENT ON TABLE reglas_pricing IS 'Instrucciones del motor. Cálculo: precio_ref = mediana del mercado (comparativas) × (1 - descuento_vs_mercado/100); piso = costo × (1 + margen_minimo/100); precio = MAX(ref, piso). Sin mercado: costo × (1 + margen_objetivo/100). La regla más específica (mayor prioridad) gana.';

CREATE TABLE presupuestos (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    proceso_comercial_id    UUID            NOT NULL,
    drogueria_id            UUID            NOT NULL,
    estado                  TEXT            NOT NULL DEFAULT 'generado',
    monto_total             NUMERIC(15, 2)  NULL,
    cantidad_items          INTEGER         NOT NULL DEFAULT 0,
    items_sin_precio        INTEGER         NOT NULL DEFAULT 0,
    generado_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    aprobado_por            UUID            NULL,
    aprobado_at             TIMESTAMPTZ     NULL,
    presentado_por          UUID            NULL,
    presentado_at           TIMESTAMPTZ     NULL,
    notas                   TEXT            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pre_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_pre_estado
        CHECK (estado IN ('generado', 'en_revision', 'aprobado', 'presentado', 'adjudicado', 'rechazado', 'vencido')),
    CONSTRAINT ck_pre_aprobado CHECK (
        estado IN ('generado', 'en_revision', 'vencido') OR
        (aprobado_at IS NOT NULL AND aprobado_por IS NOT NULL)
    )
);

CREATE TABLE presupuesto_items (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    presupuesto_id              UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    item_proceso_id             UUID            NOT NULL,
    producto_id                 UUID            NULL,
    precio_unitario             NUMERIC(15, 2)  NULL,
    cantidad_ofertada           NUMERIC(12, 2)  NULL,
    monto_total                 NUMERIC(15, 2)  GENERATED ALWAYS AS (precio_unitario * cantidad_ofertada) STORED,
    -- trazabilidad del cálculo
    regla_pricing_id            UUID            NULL,
    metodo_precio               TEXT            NULL,
    costo_usado                 NUMERIC(15, 2)  NULL,
    origen_costo                TEXT            NULL,
    precio_proveedor_id         UUID            NULL,
    mantenimiento_hasta_usado   DATE            NULL,
    precio_mercado_usado        NUMERIC(15, 2)  NULL,
    margen_resultante_pct       NUMERIC(7, 2)   NULL,
    detalle_calculo             JSONB           NULL,
    -- stock (solo procesos clase = cotizacion)
    stock_verificado            BOOLEAN         NOT NULL DEFAULT FALSE,
    stock_al_generar            NUMERIC(12, 2)  NULL,
    -- intervención humana
    precio_ajustado_por         UUID            NULL,
    precio_original_motor       NUMERIC(15, 2)  NULL,
    excluido                    BOOLEAN         NOT NULL DEFAULT FALSE,
    motivo_exclusion            TEXT            NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_pi UNIQUE (presupuesto_id, item_proceso_id),
    CONSTRAINT ck_pi_metodo CHECK (metodo_precio IS NULL OR metodo_precio IN ('mercado', 'piso_margen', 'margen_objetivo', 'manual', 'sin_precio')),
    CONSTRAINT ck_pi_origen CHECK (origen_costo IS NULL OR origen_costo IN ('costo_estandar', 'precio_especial'))
);

COMMENT ON COLUMN presupuesto_items.stock_verificado IS 'TRUE solo en procesos clase = cotizacion (entrega inmediata). En licitaciones no se valida stock.';


-- =============================================================================
-- CAPA 7 — COMPARATIVAS (negocio, se crean al validar la extracción)
-- =============================================================================

CREATE TABLE comparativas (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    proceso_comercial_id    UUID            NOT NULL,
    drogueria_id            UUID            NOT NULL,
    extraction_id           UUID            NULL,
    cantidad_proveedores    INTEGER         NOT NULL DEFAULT 0,
    items_analizados        INTEGER         NOT NULL DEFAULT 0,
    participamos            BOOLEAN         NOT NULL DEFAULT FALSE,
    version_numero          INTEGER         NOT NULL DEFAULT 1,
    es_vigente              BOOLEAN         NOT NULL DEFAULT TRUE,
    reemplaza_id            UUID            NULL,
    motivo_version          TEXT            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_comp_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_comp_version CHECK (version_numero >= 1),
    CONSTRAINT ck_comp_motivo CHECK ((reemplaza_id IS NULL AND motivo_version IS NULL) OR (reemplaza_id IS NOT NULL))
);

COMMENT ON TABLE comparativas IS 'Entidad de NEGOCIO: se crea al validar la extracción. Lo documental (archivo, hash, estado de procesamiento) vive en extraction_results, referenciado por extraction_id.';

CREATE TABLE ofertas_items (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    comparativa_id          UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    item_proceso_id         UUID            NULL,
    renglon_id              TEXT            NULL,
    proveedor               TEXT            NOT NULL,
    proveedor_id            UUID            NULL,
    es_drogueria_propia     BOOLEAN         NOT NULL DEFAULT FALSE,
    descripcion             TEXT            NULL,
    precio_unitario         NUMERIC(15, 2)  NOT NULL,
    cantidad_ofertada       NUMERIC(12, 2)  NULL,
    adjudicacion_estimada   BOOLEAN         NOT NULL DEFAULT FALSE,
    adjudicada              BOOLEAN         NOT NULL DEFAULT FALSE,
    posicion_precio         INTEGER         NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

COMMENT ON COLUMN ofertas_items.adjudicacion_estimada IS 'TRUE en el más barato del renglón (anticipación de compras). adjudicada = confirmado oficial por OC.';


-- =============================================================================
-- CAPA 8 — ÓRDENES DE COMPRA Y ENTREGAS (negocio)
-- =============================================================================

CREATE TABLE ordenes_compra (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    proceso_comercial_id    UUID            NOT NULL,
    cliente_id              UUID            NULL,
    drogueria_id            UUID            NOT NULL,
    extraction_id           UUID            NULL,
    numero_oc               TEXT            NOT NULL,
    estado                  TEXT            NOT NULL DEFAULT 'pendiente',
    monto_total             NUMERIC(15, 2)  NULL,
    items_cantidad          INTEGER         NOT NULL DEFAULT 0,
    fecha_emision           DATE            NULL,
    fecha_entrega_estimada  DATE            NULL,
    cantidad_entregas       INTEGER         NOT NULL DEFAULT 1,
    direccion_entrega       TEXT            NULL,
    notas                   TEXT            NULL,
    version_numero          INTEGER         NOT NULL DEFAULT 1,
    es_vigente              BOOLEAN         NOT NULL DEFAULT TRUE,
    reemplaza_id            UUID            NULL,
    motivo_version          TEXT            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_oc_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_oc UNIQUE (numero_oc, version_numero),
    CONSTRAINT ck_oc_estado
        CHECK (estado IN ('pendiente', 'emitida', 'en_entrega', 'parcialmente_entregada', 'entregada', 'cancelada')),
    CONSTRAINT ck_oc_version CHECK (version_numero >= 1),
    CONSTRAINT ck_oc_motivo CHECK ((reemplaza_id IS NULL AND motivo_version IS NULL) OR (reemplaza_id IS NOT NULL))
);

CREATE TABLE oc_items (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    orden_compra_id     UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    oferta_item_id      UUID            NULL,
    producto_id         UUID            NULL,
    numero_renglon      INTEGER         NOT NULL,
    descripcion         TEXT            NOT NULL,
    cantidad            NUMERIC(12, 2)  NOT NULL,
    precio_unitario     NUMERIC(15, 2)  NOT NULL,
    monto_total         NUMERIC(15, 2)  GENERATED ALWAYS AS (precio_unitario * cantidad) STORED,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_oci UNIQUE (orden_compra_id, numero_renglon)
);

COMMENT ON COLUMN oc_items.producto_id IS 'Link al catálogo. Cierra la trazabilidad producto → oferta → OC → entrega y permite descontar stock del producto correcto.';

CREATE TABLE entregas_oc (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    orden_compra_id             UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    numero_entrega              INTEGER         NOT NULL,
    fecha_entrega_planificada   DATE            NULL,
    fecha_entrega_real          DATE            NULL,
    cantidad_items              INTEGER         NOT NULL DEFAULT 0,
    estado                      TEXT            NOT NULL DEFAULT 'pendiente',
    observaciones               TEXT            NULL,
    comprobante_entrega         TEXT            NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_eoc_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_eoc UNIQUE (orden_compra_id, numero_entrega),
    CONSTRAINT ck_eoc_estado CHECK (estado IN ('pendiente', 'en_transito', 'entregada', 'rechazada', 'parcial'))
);

CREATE TABLE entregas_oc_items (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    entrega_oc_id       UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    oc_item_id          UUID            NOT NULL,
    cantidad_entregada  NUMERIC(12, 2)  NOT NULL,
    cantidad_rechazada  NUMERIC(12, 2)  NOT NULL DEFAULT 0,
    motivo_rechazo      TEXT            NULL,
    lote                TEXT            NULL,
    vencimiento         DATE            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_eoci UNIQUE (entrega_oc_id, oc_item_id),
    CONSTRAINT ck_eoci_cant CHECK (cantidad_entregada >= 0 AND cantidad_rechazada >= 0)
);

-- Compras reales a proveedores: a quién le compraste efectivamente al ganar.
-- Cierra el círculo: precio especial ofertado → compra concreta.
CREATE TABLE compras_proveedor (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    proveedor_id            UUID            NOT NULL,
    producto_id             UUID            NOT NULL,
    proceso_comercial_id    UUID            NULL,
    oc_item_id              UUID            NULL,
    precio_proveedor_id     UUID            NULL,
    cantidad                NUMERIC(12, 2)  NOT NULL,
    precio_unitario         NUMERIC(15, 2)  NOT NULL,
    monto_total             NUMERIC(15, 2)  GENERATED ALWAYS AS (precio_unitario * cantidad) STORED,
    fecha_compra            DATE            NOT NULL DEFAULT CURRENT_DATE,
    numero_documento        TEXT            NULL,
    plazo_pago_dias         INTEGER         NULL,
    notas                   TEXT            NULL,
    creado_por              UUID            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_cp_cant CHECK (cantidad > 0),
    CONSTRAINT ck_cp_precio CHECK (precio_unitario >= 0)
);

COMMENT ON TABLE compras_proveedor IS 'La compra efectiva al proveedor una vez ganado el proceso. precio_proveedor_id linkea a la oferta especial si la hubo: permite comparar precio cotizado vs precio real de compra.';


-- =============================================================================
-- MOTOR DE EVENTOS OPERATIVOS
-- =============================================================================

CREATE TABLE eventos (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    tipo                    TEXT            NOT NULL,
    titulo                  TEXT            NOT NULL,
    descripcion             TEXT            NULL,
    estado                  TEXT            NOT NULL DEFAULT 'pendiente',
    prioridad               TEXT            NOT NULL DEFAULT 'media',
    origen                  TEXT            NOT NULL DEFAULT 'usuario',
    -- relaciones opcionales (un evento puede colgar de varias)
    proceso_comercial_id    UUID            NULL,
    comparativa_id          UUID            NULL,
    orden_compra_id         UUID            NULL,
    cliente_id              UUID            NULL,
    proveedor_id            UUID            NULL,
    responsable_id          UUID            NULL,
    -- dependencia lineal: un evento espera a UN evento anterior
    depende_de_id           UUID            NULL,
    -- si nació de una plantilla recurrente
    evento_recurrente_id    UUID            NULL,
    -- fechas
    fecha_programada        TIMESTAMPTZ     NULL,
    fecha_limite            TIMESTAMPTZ     NULL,
    fecha_real              TIMESTAMPTZ     NULL,
    -- extensibilidad
    metadata                JSONB           NULL,
    regla_automatizacion_id UUID            NULL,
    -- auditoría + soft delete
    created_by              UUID            NULL,
    updated_by              UUID            NULL,
    deleted_at              TIMESTAMPTZ     NULL,
    deleted_by              UUID            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_ev_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT ck_eventos_tipo CHECK (tipo IN (
        'compra', 'recepcion', 'entrega', 'seguimiento', 'reclamo',
        'facturacion', 'pago', 'llamada', 'reunion', 'recordatorio',
        'vencimiento', 'observacion', 'otro'
    )),
    CONSTRAINT ck_eventos_estado CHECK (estado IN (
        'pendiente', 'bloqueado', 'en_progreso', 'completado', 'cancelado', 'vencido'
    )),
    CONSTRAINT ck_eventos_prioridad CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
    CONSTRAINT ck_eventos_origen CHECK (origen IN ('usuario', 'ia', 'sistema', 'automatico')),
    CONSTRAINT ck_eventos_fechas CHECK (
        fecha_limite IS NULL OR fecha_programada IS NULL OR fecha_limite >= fecha_programada
    ),
    CONSTRAINT ck_eventos_no_self CHECK (depende_de_id IS NULL OR depende_de_id != id)
);

COMMENT ON TABLE eventos IS 'Motor de eventos operativos. Cada evento es una tarea/acción dentro del proceso comercial, no una simple entrada de calendario. El calendario del sistema es una vista sobre esta tabla.';
COMMENT ON COLUMN eventos.origen         IS 'usuario: lo creó una persona. ia: lo generó un agente de IA. sistema: lo generó el backend. automatico: lo disparó una regla_automatizacion.';
COMMENT ON COLUMN eventos.estado         IS 'bloqueado: el evento no puede avanzar porque depende de otro sin completar (ver depende_de_id). Lo setea el backend, no la BD.';
COMMENT ON COLUMN eventos.depende_de_id  IS 'Evento que debe completarse ANTES que este. NULL = no depende de nadie. Flujos reales son lineales; si algún día se necesita esperar a VARIOS, se migra a una tabla evento_dependencias sin tocar el resto.';
COMMENT ON COLUMN eventos.metadata       IS 'JSONB para datos específicos del tipo de evento sin cambiar el esquema (ej: número de factura, monto, teléfono llamado).';


-- =============================================================================
-- EVENTOS RECURRENTES (plantilla → instancias en "eventos")
-- =============================================================================

CREATE TABLE eventos_recurrentes (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    tipo                    TEXT            NOT NULL,
    titulo                  TEXT            NOT NULL,
    descripcion             TEXT            NULL,
    prioridad               TEXT            NOT NULL DEFAULT 'media',
    responsable_id          UUID            NULL,
    cliente_id              UUID            NULL,
    proveedor_id            UUID            NULL,
    metadata                JSONB           NULL,
    rrule                   TEXT            NOT NULL,
    fecha_inicio            DATE            NOT NULL,
    fecha_fin               DATE            NULL,
    proxima_ejecucion       TIMESTAMPTZ     NULL,
    ultima_generacion       TIMESTAMPTZ     NULL,
    instancias_generadas    INTEGER         NOT NULL DEFAULT 0,
    activa                  BOOLEAN         NOT NULL DEFAULT TRUE,
    created_by              UUID            NULL,
    updated_by              UUID            NULL,
    deleted_at              TIMESTAMPTZ     NULL,
    deleted_by              UUID            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_er_tipo CHECK (tipo IN (
        'compra', 'recepcion', 'entrega', 'seguimiento', 'reclamo',
        'facturacion', 'pago', 'llamada', 'reunion', 'recordatorio',
        'vencimiento', 'observacion', 'otro'
    )),
    CONSTRAINT ck_er_prioridad CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
    CONSTRAINT ck_er_fechas CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
    CONSTRAINT ck_er_instancias CHECK (instancias_generadas >= 0)
);

COMMENT ON TABLE eventos_recurrentes IS 'Plantilla de eventos que se repiten (revisar stock los lunes, control mensual). Un job del backend lee proxima_ejecucion, materializa una instancia en "eventos" y recalcula la próxima con la rrule (dateutil.rrule).';
COMMENT ON COLUMN eventos_recurrentes.rrule IS 'Regla de repetición en formato RFC 5545 (iCalendar). Ej: FREQ=WEEKLY;BYDAY=MO.';
COMMENT ON COLUMN eventos_recurrentes.proxima_ejecucion IS 'Cuándo generar la próxima instancia. Única columna que el scheduler consulta, por eso indexada.';


-- =============================================================================
-- HISTORIAL DE CAMBIOS (auditoría unificada, INSERT-only)
-- FKs específicas nullable + CHECK de exactamente una entidad.
-- =============================================================================

CREATE TABLE historial_cambios (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    proceso_comercial_id    UUID            NULL,
    comparativa_id          UUID            NULL,
    orden_compra_id         UUID            NULL,
    presupuesto_id          UUID            NULL,
    evento_id               UUID            NULL,
    tipo_cambio             TEXT            NOT NULL,
    campo                   TEXT            NULL,
    valor_anterior          TEXT            NULL,
    valor_nuevo             TEXT            NULL,
    batch_id                UUID            NULL,
    usuario_id              UUID            NULL,
    origen                  TEXT            NOT NULL DEFAULT 'usuario',
    observaciones           TEXT            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_hc_una_entidad CHECK (
        (proceso_comercial_id IS NOT NULL)::int +
        (comparativa_id IS NOT NULL)::int +
        (orden_compra_id IS NOT NULL)::int +
        (presupuesto_id IS NOT NULL)::int +
        (evento_id IS NOT NULL)::int = 1
    ),
    CONSTRAINT ck_hc_tipo_cambio CHECK (tipo_cambio IN ('estado', 'campo', 'creacion', 'eliminacion', 'restauracion')),
    CONSTRAINT ck_hc_campo CHECK (
        tipo_cambio IN ('creacion', 'eliminacion', 'restauracion') OR campo IS NOT NULL
    ),
    CONSTRAINT ck_hc_origen CHECK (origen IN ('usuario', 'ia', 'automatizacion', 'webhook', 'api', 'sistema'))
);

COMMENT ON TABLE historial_cambios IS 'Auditoría unificada. El historial de estados es un caso particular (tipo_cambio=estado, campo=estado). Un UPDATE que toca N campos genera N filas con el mismo batch_id. valor_anterior/valor_nuevo son TEXT: común denominador de cualquier tipo de columna auditada. Tabla INSERT-only, nunca se actualiza ni borra una fila.';
COMMENT ON COLUMN historial_cambios.batch_id IS 'Agrupa todas las filas generadas por un mismo guardado/UPDATE.';
COMMENT ON COLUMN historial_cambios.origen   IS 'Desde dónde se originó el cambio. usuario_id responde QUIÉN, origen responde CÓMO.';


-- =============================================================================
-- MOTOR DE REGLAS DE AUTOMATIZACIÓN (modelo, sin lógica en la BD)
-- =============================================================================

CREATE TABLE reglas_automatizacion (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID            NOT NULL,
    nombre              TEXT            NOT NULL,
    descripcion         TEXT            NULL,
    evento_disparador   TEXT            NOT NULL,
    entidad_objetivo    TEXT            NOT NULL,
    condicion           JSONB           NULL,
    tipo_accion         TEXT            NOT NULL,
    parametros_accion   JSONB           NULL,
    modo_ejecucion      TEXT            NOT NULL DEFAULT 'cola',
    max_reintentos      INTEGER         NOT NULL DEFAULT 3,
    activa              BOOLEAN         NOT NULL DEFAULT TRUE,
    prioridad           INTEGER         NOT NULL DEFAULT 0,
    created_by          UUID            NULL,
    updated_by          UUID            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_ra_entidad CHECK (entidad_objetivo IN (
        'proceso_comercial', 'comparativa', 'orden_compra', 'presupuesto',
        'evento', 'extraction_result', 'entrega'
    )),
    CONSTRAINT ck_ra_tipo_accion CHECK (tipo_accion IN (
        'crear_evento', 'crear_oc', 'enviar_notificacion', 'enviar_email',
        'enviar_whatsapp', 'ejecutar_agente_ia', 'cambiar_estado', 'webhook'
    )),
    CONSTRAINT ck_ra_modo CHECK (modo_ejecucion IN ('inmediato', 'cola')),
    CONSTRAINT ck_ra_reintentos CHECK (max_reintentos >= 0 AND max_reintentos <= 10),
    CONSTRAINT ck_ra_prioridad CHECK (prioridad >= 0)
);

COMMENT ON TABLE reglas_automatizacion IS 'Reglas "cuando ocurre X → ejecutar Y". Sin versionado (deliberado: no hay reglas en producción para justificarlo — acciones_ejecutadas.regla_id ya apunta a la FILA de la regla, así que agregar versionado después no requiere migrar datos).';
COMMENT ON COLUMN reglas_automatizacion.modo_ejecucion IS 'inmediato: el backend ejecuta sincrónicamente. cola: se inserta en acciones_ejecutadas con estado=pendiente y lo toma un worker.';


-- =============================================================================
-- ACCIONES EJECUTADAS (cola + log + métricas)
-- =============================================================================

CREATE TABLE acciones_ejecutadas (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    regla_id                UUID            NULL,
    proceso_comercial_id    UUID            NULL,
    comparativa_id          UUID            NULL,
    orden_compra_id         UUID            NULL,
    presupuesto_id          UUID            NULL,
    evento_id               UUID            NULL,
    tipo_accion             TEXT            NOT NULL,
    estado                  TEXT            NOT NULL DEFAULT 'pendiente',
    resultado               JSONB           NULL,
    error_msg               TEXT            NULL,
    intentos                INTEGER         NOT NULL DEFAULT 0,
    -- métricas
    iniciado_at             TIMESTAMPTZ     NULL,
    finalizado_at           TIMESTAMPTZ     NULL,
    duracion_ms             INTEGER         NULL,
    proximo_intento_at      TIMESTAMPTZ     NULL,
    ejecutado_at            TIMESTAMPTZ     NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_ae_estado CHECK (estado IN ('pendiente', 'ejecutando', 'completada', 'fallida', 'cancelada')),
    CONSTRAINT ck_ae_una_entidad CHECK (
        (proceso_comercial_id IS NOT NULL)::int +
        (comparativa_id IS NOT NULL)::int +
        (orden_compra_id IS NOT NULL)::int +
        (presupuesto_id IS NOT NULL)::int +
        (evento_id IS NOT NULL)::int = 1
    ),
    CONSTRAINT ck_ae_duracion CHECK (duracion_ms IS NULL OR duracion_ms >= 0),
    CONSTRAINT ck_ae_intentos CHECK (intentos >= 0),
    CONSTRAINT ck_ae_fechas CHECK (
        finalizado_at IS NULL OR iniciado_at IS NULL OR finalizado_at >= iniciado_at
    )
);

COMMENT ON TABLE acciones_ejecutadas IS 'Log de acciones disparadas por reglas. estado=pendiente permite que un worker las procese; completada/fallida evita re-ejecución.';
COMMENT ON COLUMN acciones_ejecutadas.duracion_ms        IS 'Duración de la ejecución en milisegundos, completada por el backend al terminar. Permite medir rendimiento de agentes/automatizaciones.';
COMMENT ON COLUMN acciones_ejecutadas.proximo_intento_at IS 'Cuándo reintentar si falló (backoff exponencial). El worker levanta pendientes con proximo_intento_at <= NOW().';


-- =============================================================================
-- ALIAS DE PROVEEDORES (espejo de cliente_producto_alias)
-- =============================================================================

CREATE TABLE proveedor_producto_alias (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    proveedor_id                UUID            NOT NULL,
    drogueria_id                UUID            NOT NULL,
    producto_id                 UUID            NOT NULL,
    descripcion_original        TEXT            NOT NULL,
    descripcion_normalizada     TEXT            NOT NULL,
    veces_usado                 INTEGER         NOT NULL DEFAULT 1,
    ultimo_uso_at               TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    vigente                     BOOLEAN         NOT NULL DEFAULT TRUE,
    creado_por                  UUID            NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_ppa_veces CHECK (veces_usado >= 0)
);

COMMENT ON TABLE proveedor_producto_alias IS 'Memoria de matching descripción→producto por PROVEEDOR (espejo de cliente_producto_alias). Distintos proveedores nombran el mismo producto de formas diferentes; mejora el matching de comparativas.';


-- =============================================================================
-- CENTRO DE NOTIFICACIONES (separado de eventos: evento=trabajo, notificación=aviso)
-- =============================================================================

CREATE TABLE notificaciones (
    id                      UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id            UUID            NOT NULL,
    destinatario_id         UUID            NOT NULL,
    tipo                    TEXT            NOT NULL,
    titulo                  TEXT            NOT NULL,
    mensaje                 TEXT            NULL,
    prioridad               TEXT            NOT NULL DEFAULT 'media',
    url_destino             TEXT            NULL,
    origen                  TEXT            NOT NULL DEFAULT 'sistema',
    proceso_comercial_id    UUID            NULL,
    comparativa_id          UUID            NULL,
    orden_compra_id         UUID            NULL,
    presupuesto_id          UUID            NULL,
    evento_id               UUID            NULL,
    accion_ejecutada_id     UUID            NULL,
    leida_at                TIMESTAMPTZ     NULL,
    archivada_at            TIMESTAMPTZ     NULL,
    metadata                JSONB           NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_notif_tipo CHECK (tipo IN (
        'oc_creada', 'evento_vencido', 'evento_asignado', 'ia_completada',
        'error_automatizacion', 'comparativa_disponible', 'presupuesto_aprobado',
        'presupuesto_pendiente', 'proceso_por_vencer', 'entrega_atrasada',
        'precio_por_vencer', 'sistema', 'otro'
    )),
    CONSTRAINT ck_notif_prioridad CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
    CONSTRAINT ck_notif_origen CHECK (origen IN ('usuario', 'ia', 'automatizacion', 'webhook', 'api', 'sistema'))
);

COMMENT ON TABLE notificaciones IS 'Centro de notificaciones. Un EVENTO es trabajo (tiene responsable, fechas, estado); una NOTIFICACIÓN es un aviso (se lee y se archiva). Las entregas por canal viven en notificacion_entregas.';

CREATE TABLE notificacion_entregas (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    notificacion_id     UUID            NOT NULL,
    drogueria_id        UUID            NOT NULL,
    canal               TEXT            NOT NULL,
    estado              TEXT            NOT NULL DEFAULT 'pendiente',
    destino             TEXT            NULL,
    proveedor_externo   TEXT            NULL,
    referencia_externa  TEXT            NULL,
    intentos            INTEGER         NOT NULL DEFAULT 0,
    enviado_at          TIMESTAMPTZ     NULL,
    error_msg           TEXT            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_notif_canal UNIQUE (notificacion_id, canal),
    CONSTRAINT ck_ne_canal CHECK (canal IN ('web', 'email', 'whatsapp', 'sms', 'push', 'webhook')),
    CONSTRAINT ck_ne_estado CHECK (estado IN ('pendiente', 'enviando', 'enviada', 'fallida', 'cancelada')),
    CONSTRAINT ck_ne_intentos CHECK (intentos >= 0)
);

COMMENT ON TABLE notificacion_entregas IS 'Una fila por canal de envío. Permite que la misma notificación esté leída en la web, enviada por mail y fallida en WhatsApp, cada una con su estado.';

CREATE TABLE notificacion_preferencias (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    usuario_id          UUID            NOT NULL,
    drogueria_id        UUID            NOT NULL,
    tipo                TEXT            NOT NULL,
    canal               TEXT            NOT NULL,
    habilitada          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_notif_pref UNIQUE (usuario_id, tipo, canal),
    CONSTRAINT ck_np_canal CHECK (canal IN ('web', 'email', 'whatsapp', 'sms', 'push', 'webhook'))
);

COMMENT ON TABLE notificacion_preferencias IS 'Qué notificaciones quiere recibir cada usuario y por qué canal. Sin fila = default del backend.';


-- =============================================================================
-- FOREIGN KEYS
-- =============================================================================

ALTER TABLE clientes                    ADD CONSTRAINT fk_cli_drog    FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE cliente_contactos           ADD CONSTRAINT fk_cc_cli      FOREIGN KEY (cliente_id, drogueria_id) REFERENCES clientes (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE cliente_observaciones       ADD CONSTRAINT fk_cobs_cli    FOREIGN KEY (cliente_id)   REFERENCES clientes (id) ON DELETE CASCADE;
ALTER TABLE cliente_observaciones       ADD CONSTRAINT fk_cobs_drog   FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE cliente_formato_documentos  ADD CONSTRAINT fk_cfmt_cli    FOREIGN KEY (cliente_id)   REFERENCES clientes (id) ON DELETE CASCADE;
ALTER TABLE cliente_formato_documentos  ADD CONSTRAINT fk_cfmt_drog   FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE proveedores                 ADD CONSTRAINT fk_prov_drog   FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);

ALTER TABLE categorias                  ADD CONSTRAINT fk_cat_drog    FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE productos                   ADD CONSTRAINT fk_prod_drog   FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE productos                   ADD CONSTRAINT fk_prod_cat    FOREIGN KEY (categoria_id) REFERENCES categorias (id);
ALTER TABLE costos_productos            ADD CONSTRAINT fk_cost_prod   FOREIGN KEY (producto_id)  REFERENCES productos (id) ON DELETE CASCADE;
ALTER TABLE costos_productos            ADD CONSTRAINT fk_cost_drog   FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE stock_productos             ADD CONSTRAINT fk_stock_prod  FOREIGN KEY (producto_id)  REFERENCES productos (id) ON DELETE CASCADE;
ALTER TABLE stock_productos             ADD CONSTRAINT fk_stock_drog  FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE cliente_producto_alias      ADD CONSTRAINT fk_alias_cli   FOREIGN KEY (cliente_id, drogueria_id) REFERENCES clientes (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE cliente_producto_alias      ADD CONSTRAINT fk_alias_prod  FOREIGN KEY (producto_id)  REFERENCES productos (id);
ALTER TABLE precios_proveedor           ADD CONSTRAINT fk_pp_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE precios_proveedor           ADD CONSTRAINT fk_pp_prov     FOREIGN KEY (proveedor_id) REFERENCES proveedores (id);
ALTER TABLE precios_proveedor           ADD CONSTRAINT fk_pp_prod     FOREIGN KEY (producto_id)  REFERENCES productos (id);
ALTER TABLE precios_proveedor           ADD CONSTRAINT fk_pp_item     FOREIGN KEY (item_proceso_id) REFERENCES items_proceso (id) ON DELETE CASCADE;

ALTER TABLE procesos_comerciales        ADD CONSTRAINT fk_proc_drog   FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE procesos_comerciales        ADD CONSTRAINT fk_proc_cli    FOREIGN KEY (cliente_id)   REFERENCES clientes (id);
ALTER TABLE procesos_comerciales        ADD CONSTRAINT fk_proc_cat    FOREIGN KEY (categoria_id) REFERENCES categorias (id);

ALTER TABLE processing_sessions         ADD CONSTRAINT fk_ps_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE processing_sessions         ADD CONSTRAINT fk_ps_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE processing_sessions         ADD CONSTRAINT fk_ps_fmt      FOREIGN KEY (formato_usado_id)     REFERENCES cliente_formato_documentos (id);
ALTER TABLE extraction_results          ADD CONSTRAINT fk_er_sess     FOREIGN KEY (session_id)           REFERENCES processing_sessions (id);
ALTER TABLE extraction_results          ADD CONSTRAINT fk_er_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE extraction_results          ADD CONSTRAINT fk_er_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE chunk_results               ADD CONSTRAINT fk_ch_sess     FOREIGN KEY (session_id, drogueria_id) REFERENCES processing_sessions (id, drogueria_id) ON DELETE CASCADE;

ALTER TABLE items_proceso               ADD CONSTRAINT fk_ip_proc     FOREIGN KEY (proceso_comercial_id, drogueria_id) REFERENCES procesos_comerciales (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE items_proceso               ADD CONSTRAINT fk_ip_extr     FOREIGN KEY (extraction_id)        REFERENCES extraction_results (id);
ALTER TABLE items_proceso               ADD CONSTRAINT fk_ip_prod     FOREIGN KEY (producto_id)          REFERENCES productos (id);
ALTER TABLE items_proceso               ADD CONSTRAINT fk_ip_alias    FOREIGN KEY (alias_id)             REFERENCES cliente_producto_alias (id);
ALTER TABLE matching_candidatos         ADD CONSTRAINT fk_mc_item     FOREIGN KEY (item_proceso_id, drogueria_id) REFERENCES items_proceso (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE matching_candidatos         ADD CONSTRAINT fk_mc_prod     FOREIGN KEY (producto_id)          REFERENCES productos (id);

ALTER TABLE reglas_pricing              ADD CONSTRAINT fk_rp_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE reglas_pricing              ADD CONSTRAINT fk_rp_cli      FOREIGN KEY (cliente_id)   REFERENCES clientes (id);
ALTER TABLE reglas_pricing              ADD CONSTRAINT fk_rp_cat      FOREIGN KEY (categoria_id) REFERENCES categorias (id);

ALTER TABLE presupuestos                ADD CONSTRAINT fk_pre_proc    FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE presupuestos                ADD CONSTRAINT fk_pre_drog    FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE presupuesto_items           ADD CONSTRAINT fk_pi_pre      FOREIGN KEY (presupuesto_id, drogueria_id) REFERENCES presupuestos (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE presupuesto_items           ADD CONSTRAINT fk_pi_item     FOREIGN KEY (item_proceso_id)      REFERENCES items_proceso (id);
ALTER TABLE presupuesto_items           ADD CONSTRAINT fk_pi_prod     FOREIGN KEY (producto_id)          REFERENCES productos (id);
ALTER TABLE presupuesto_items           ADD CONSTRAINT fk_pi_regla    FOREIGN KEY (regla_pricing_id)     REFERENCES reglas_pricing (id);
ALTER TABLE presupuesto_items           ADD CONSTRAINT fk_pi_pp       FOREIGN KEY (precio_proveedor_id)  REFERENCES precios_proveedor (id);

ALTER TABLE comparativas                ADD CONSTRAINT fk_comp_proc   FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE comparativas                ADD CONSTRAINT fk_comp_drog   FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE comparativas                ADD CONSTRAINT fk_comp_extr   FOREIGN KEY (extraction_id)        REFERENCES extraction_results (id);
ALTER TABLE comparativas                ADD CONSTRAINT fk_comp_reempl FOREIGN KEY (reemplaza_id)         REFERENCES comparativas (id);
ALTER TABLE ofertas_items               ADD CONSTRAINT fk_oi_comp     FOREIGN KEY (comparativa_id, drogueria_id) REFERENCES comparativas (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE ofertas_items               ADD CONSTRAINT fk_oi_item     FOREIGN KEY (item_proceso_id)      REFERENCES items_proceso (id);
ALTER TABLE ofertas_items               ADD CONSTRAINT fk_oi_prov     FOREIGN KEY (proveedor_id)         REFERENCES proveedores (id);

ALTER TABLE ordenes_compra              ADD CONSTRAINT fk_oc_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE ordenes_compra              ADD CONSTRAINT fk_oc_cli      FOREIGN KEY (cliente_id)           REFERENCES clientes (id);
ALTER TABLE ordenes_compra              ADD CONSTRAINT fk_oc_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE ordenes_compra              ADD CONSTRAINT fk_oc_extr     FOREIGN KEY (extraction_id)        REFERENCES extraction_results (id);
ALTER TABLE ordenes_compra              ADD CONSTRAINT fk_oc_reempl   FOREIGN KEY (reemplaza_id)         REFERENCES ordenes_compra (id);
ALTER TABLE oc_items                    ADD CONSTRAINT fk_oci_oc      FOREIGN KEY (orden_compra_id, drogueria_id) REFERENCES ordenes_compra (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE oc_items                    ADD CONSTRAINT fk_oci_oferta  FOREIGN KEY (oferta_item_id)       REFERENCES ofertas_items (id);
ALTER TABLE oc_items                    ADD CONSTRAINT fk_oci_prod    FOREIGN KEY (producto_id)          REFERENCES productos (id);
ALTER TABLE entregas_oc                 ADD CONSTRAINT fk_eoc_oc      FOREIGN KEY (orden_compra_id, drogueria_id) REFERENCES ordenes_compra (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE entregas_oc_items           ADD CONSTRAINT fk_eoci_ent    FOREIGN KEY (entrega_oc_id, drogueria_id) REFERENCES entregas_oc (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE entregas_oc_items           ADD CONSTRAINT fk_eoci_oci    FOREIGN KEY (oc_item_id)           REFERENCES oc_items (id);

ALTER TABLE compras_proveedor           ADD CONSTRAINT fk_cp_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE compras_proveedor           ADD CONSTRAINT fk_cp_prov     FOREIGN KEY (proveedor_id)         REFERENCES proveedores (id);
ALTER TABLE compras_proveedor           ADD CONSTRAINT fk_cp_prod     FOREIGN KEY (producto_id)          REFERENCES productos (id);
ALTER TABLE compras_proveedor           ADD CONSTRAINT fk_cp_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE compras_proveedor           ADD CONSTRAINT fk_cp_oci      FOREIGN KEY (oc_item_id)           REFERENCES oc_items (id);
ALTER TABLE compras_proveedor           ADD CONSTRAINT fk_cp_pp       FOREIGN KEY (precio_proveedor_id)  REFERENCES precios_proveedor (id);

-- Eventos, automatizaciones, notificaciones: FKs que NO dependen de "usuarios"
-- (usuarios se crea en rls_final.sql; las FKs hacia usuarios están ahí también,
-- en una sección aparte que corre después de crear esa tabla).
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_comp     FOREIGN KEY (comparativa_id)       REFERENCES comparativas (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_oc       FOREIGN KEY (orden_compra_id)      REFERENCES ordenes_compra (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_cli      FOREIGN KEY (cliente_id)           REFERENCES clientes (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_prov     FOREIGN KEY (proveedor_id)         REFERENCES proveedores (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_depende  FOREIGN KEY (depende_de_id)        REFERENCES eventos (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_recurr   FOREIGN KEY (evento_recurrente_id) REFERENCES eventos_recurrentes (id);
ALTER TABLE eventos                     ADD CONSTRAINT fk_ev_regla    FOREIGN KEY (regla_automatizacion_id) REFERENCES reglas_automatizacion (id);

ALTER TABLE eventos_recurrentes         ADD CONSTRAINT fk_evr_drog    FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);
ALTER TABLE eventos_recurrentes         ADD CONSTRAINT fk_evr_cli     FOREIGN KEY (cliente_id)   REFERENCES clientes (id);
ALTER TABLE eventos_recurrentes         ADD CONSTRAINT fk_evr_prov    FOREIGN KEY (proveedor_id) REFERENCES proveedores (id);

ALTER TABLE historial_cambios           ADD CONSTRAINT fk_hc_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE historial_cambios           ADD CONSTRAINT fk_hc_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE historial_cambios           ADD CONSTRAINT fk_hc_comp     FOREIGN KEY (comparativa_id)       REFERENCES comparativas (id);
ALTER TABLE historial_cambios           ADD CONSTRAINT fk_hc_oc       FOREIGN KEY (orden_compra_id)      REFERENCES ordenes_compra (id);
ALTER TABLE historial_cambios           ADD CONSTRAINT fk_hc_pre      FOREIGN KEY (presupuesto_id)       REFERENCES presupuestos (id);
ALTER TABLE historial_cambios           ADD CONSTRAINT fk_hc_ev       FOREIGN KEY (evento_id)            REFERENCES eventos (id);

ALTER TABLE reglas_automatizacion       ADD CONSTRAINT fk_ra_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);

ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_regla    FOREIGN KEY (regla_id)             REFERENCES reglas_automatizacion (id);
ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_comp     FOREIGN KEY (comparativa_id)       REFERENCES comparativas (id);
ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_oc       FOREIGN KEY (orden_compra_id)      REFERENCES ordenes_compra (id);
ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_pre      FOREIGN KEY (presupuesto_id)       REFERENCES presupuestos (id);
ALTER TABLE acciones_ejecutadas         ADD CONSTRAINT fk_ae_ev       FOREIGN KEY (evento_id)            REFERENCES eventos (id);

ALTER TABLE proveedor_producto_alias    ADD CONSTRAINT fk_ppa_prov    FOREIGN KEY (proveedor_id, drogueria_id) REFERENCES proveedores (id, drogueria_id) ON DELETE CASCADE;
ALTER TABLE proveedor_producto_alias    ADD CONSTRAINT fk_ppa_prod    FOREIGN KEY (producto_id) REFERENCES productos (id);

ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_drog     FOREIGN KEY (drogueria_id)         REFERENCES droguerias (id);
ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_proc     FOREIGN KEY (proceso_comercial_id) REFERENCES procesos_comerciales (id);
ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_comp     FOREIGN KEY (comparativa_id)       REFERENCES comparativas (id);
ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_oc       FOREIGN KEY (orden_compra_id)      REFERENCES ordenes_compra (id);
ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_pre      FOREIGN KEY (presupuesto_id)       REFERENCES presupuestos (id);
ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_ev       FOREIGN KEY (evento_id)            REFERENCES eventos (id);
ALTER TABLE notificaciones              ADD CONSTRAINT fk_no_accion   FOREIGN KEY (accion_ejecutada_id)  REFERENCES acciones_ejecutadas (id);

ALTER TABLE notificacion_entregas       ADD CONSTRAINT fk_ne_notif    FOREIGN KEY (notificacion_id) REFERENCES notificaciones (id) ON DELETE CASCADE;
ALTER TABLE notificacion_entregas       ADD CONSTRAINT fk_ne_drog     FOREIGN KEY (drogueria_id)    REFERENCES droguerias (id);

ALTER TABLE notificacion_preferencias   ADD CONSTRAINT fk_np_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id);


-- =============================================================================
-- ÍNDICES
-- =============================================================================

CREATE INDEX idx_clientes_drog          ON clientes (drogueria_id);
CREATE INDEX idx_cc_cliente             ON cliente_contactos (cliente_id) WHERE activo = TRUE;
CREATE INDEX idx_cobs_cliente           ON cliente_observaciones (cliente_id, created_at DESC);
CREATE INDEX idx_cfmt_cliente           ON cliente_formato_documentos (cliente_id, doc_type) WHERE activo = TRUE;
CREATE INDEX idx_prov_drog              ON proveedores (drogueria_id);
CREATE INDEX idx_prov_compra            ON proveedores (drogueria_id) WHERE es_proveedor_compra = TRUE;

CREATE INDEX idx_cat_drog               ON categorias (drogueria_id) WHERE activa = TRUE;
CREATE INDEX idx_prod_drog              ON productos (drogueria_id);
CREATE INDEX idx_prod_codigo            ON productos (drogueria_id, codigo_interno);
CREATE INDEX idx_prod_cat               ON productos (categoria_id) WHERE activo = TRUE;
CREATE INDEX idx_cost_prod              ON costos_productos (producto_id);
CREATE INDEX idx_cost_vigente           ON costos_productos (producto_id) WHERE fecha_hasta IS NULL;
CREATE INDEX idx_stock_prod             ON stock_productos (producto_id);
CREATE INDEX idx_alias_busq             ON cliente_producto_alias (cliente_id, descripcion_normalizada) WHERE vigente = TRUE;
CREATE INDEX idx_alias_prod             ON cliente_producto_alias (producto_id);
CREATE INDEX idx_pp_prod                ON precios_proveedor (producto_id) WHERE activa = TRUE;
CREATE INDEX idx_pp_item                ON precios_proveedor (item_proceso_id) WHERE item_proceso_id IS NOT NULL;
CREATE INDEX idx_pp_vigentes            ON precios_proveedor (producto_id, mantenimiento_hasta) WHERE activa = TRUE;

CREATE INDEX idx_proc_drog              ON procesos_comerciales (drogueria_id);
CREATE INDEX idx_proc_cli               ON procesos_comerciales (cliente_id);
CREATE INDEX idx_proc_clase             ON procesos_comerciales (drogueria_id, clase);
CREATE INDEX idx_proc_estado            ON procesos_comerciales (estado);
CREATE INDEX idx_proc_venc              ON procesos_comerciales (vencimiento) WHERE vencimiento IS NOT NULL;

CREATE INDEX idx_ps_drog                ON processing_sessions (drogueria_id);
CREATE INDEX idx_ps_proc                ON processing_sessions (proceso_comercial_id);
CREATE INDEX idx_er_drog                ON extraction_results (drogueria_id);
CREATE INDEX idx_er_proc                ON extraction_results (proceso_comercial_id);
CREATE INDEX idx_er_sin_validar         ON extraction_results (drogueria_id, created_at DESC) WHERE validado = FALSE;
CREATE INDEX idx_ch_sess                ON chunk_results (session_id);

CREATE INDEX idx_ip_proc                ON items_proceso (proceso_comercial_id);
CREATE INDEX idx_ip_prod                ON items_proceso (producto_id) WHERE producto_id IS NOT NULL;
CREATE INDEX idx_ip_matching            ON items_proceso (proceso_comercial_id, estado_matching);
CREATE INDEX idx_mc_item                ON matching_candidatos (item_proceso_id);

CREATE INDEX idx_rp_drog                ON reglas_pricing (drogueria_id, prioridad DESC) WHERE activa = TRUE;
CREATE INDEX idx_pre_proc               ON presupuestos (proceso_comercial_id);
CREATE INDEX idx_pre_estado             ON presupuestos (estado);
CREATE INDEX idx_pi_pre                 ON presupuesto_items (presupuesto_id);
CREATE INDEX idx_pi_item                ON presupuesto_items (item_proceso_id);

CREATE INDEX idx_comp_proc              ON comparativas (proceso_comercial_id);
CREATE INDEX idx_comp_vigente           ON comparativas (proceso_comercial_id) WHERE es_vigente = TRUE;
CREATE INDEX idx_oi_comp                ON ofertas_items (comparativa_id);
CREATE INDEX idx_oi_item                ON ofertas_items (item_proceso_id);
CREATE INDEX idx_oi_adjudicada          ON ofertas_items (adjudicada);
CREATE INDEX idx_oi_estimada            ON ofertas_items (adjudicacion_estimada);
CREATE INDEX idx_oi_propia              ON ofertas_items (es_drogueria_propia);
CREATE INDEX idx_oi_sin_match           ON ofertas_items (proveedor) WHERE proveedor_id IS NULL AND es_drogueria_propia = FALSE;

CREATE INDEX idx_oc_proc                ON ordenes_compra (proceso_comercial_id);
CREATE INDEX idx_oc_estado              ON ordenes_compra (estado);
CREATE INDEX idx_oc_vigente             ON ordenes_compra (proceso_comercial_id) WHERE es_vigente = TRUE;
CREATE INDEX idx_oci_oc                 ON oc_items (orden_compra_id);
CREATE INDEX idx_oci_prod               ON oc_items (producto_id) WHERE producto_id IS NOT NULL;
CREATE INDEX idx_eoc_oc                 ON entregas_oc (orden_compra_id);
CREATE INDEX idx_eoc_estado             ON entregas_oc (estado);
CREATE INDEX idx_eoci_ent               ON entregas_oc_items (entrega_oc_id);
CREATE INDEX idx_eoci_lote              ON entregas_oc_items (lote) WHERE lote IS NOT NULL;

CREATE INDEX idx_cp_prov                ON compras_proveedor (proveedor_id);
CREATE INDEX idx_cp_prod                ON compras_proveedor (producto_id);
CREATE INDEX idx_cp_proc                ON compras_proveedor (proceso_comercial_id) WHERE proceso_comercial_id IS NOT NULL;

-- Índices adicionales sobre columnas de FK que quedaron sin cubrir arriba.
-- Postgres no indexa FKs automáticamente; sin esto, los JOIN contra estas
-- columnas (incluidas las políticas RLS con EXISTS(...JOIN...)) escanean
-- la tabla completa a medida que crece.
CREATE INDEX idx_cobs_drog      ON cliente_observaciones (drogueria_id);
CREATE INDEX idx_cfmt_drog      ON cliente_formato_documentos (drogueria_id);
CREATE INDEX idx_cost_drog      ON costos_productos (drogueria_id);
CREATE INDEX idx_stock_drog     ON stock_productos (drogueria_id);
CREATE INDEX idx_pp_drog        ON precios_proveedor (drogueria_id);
CREATE INDEX idx_pp_prov        ON precios_proveedor (proveedor_id);
CREATE INDEX idx_proc_categoria ON procesos_comerciales (categoria_id) WHERE categoria_id IS NOT NULL;
CREATE INDEX idx_ps_formato     ON processing_sessions (formato_usado_id) WHERE formato_usado_id IS NOT NULL;
CREATE INDEX idx_er_session     ON extraction_results (session_id) WHERE session_id IS NOT NULL;
CREATE INDEX idx_ip_extraction  ON items_proceso (extraction_id) WHERE extraction_id IS NOT NULL;
CREATE INDEX idx_ip_alias       ON items_proceso (alias_id) WHERE alias_id IS NOT NULL;
CREATE INDEX idx_mc_producto    ON matching_candidatos (producto_id);
CREATE INDEX idx_rp_cliente     ON reglas_pricing (cliente_id) WHERE cliente_id IS NOT NULL;
CREATE INDEX idx_rp_categoria   ON reglas_pricing (categoria_id) WHERE categoria_id IS NOT NULL;
CREATE INDEX idx_pre_drog       ON presupuestos (drogueria_id);
CREATE INDEX idx_pi_producto    ON presupuesto_items (producto_id) WHERE producto_id IS NOT NULL;
CREATE INDEX idx_pi_regla       ON presupuesto_items (regla_pricing_id) WHERE regla_pricing_id IS NOT NULL;
CREATE INDEX idx_pi_precio_prov ON presupuesto_items (precio_proveedor_id) WHERE precio_proveedor_id IS NOT NULL;
CREATE INDEX idx_comp_drog      ON comparativas (drogueria_id);
CREATE INDEX idx_comp_extract   ON comparativas (extraction_id) WHERE extraction_id IS NOT NULL;
CREATE INDEX idx_comp_reemplaza ON comparativas (reemplaza_id) WHERE reemplaza_id IS NOT NULL;
CREATE INDEX idx_oi_proveedor   ON ofertas_items (proveedor_id) WHERE proveedor_id IS NOT NULL;
CREATE INDEX idx_oc_cliente     ON ordenes_compra (cliente_id) WHERE cliente_id IS NOT NULL;
CREATE INDEX idx_oc_drog        ON ordenes_compra (drogueria_id);
CREATE INDEX idx_oc_extraction  ON ordenes_compra (extraction_id) WHERE extraction_id IS NOT NULL;
CREATE INDEX idx_oc_reemplaza   ON ordenes_compra (reemplaza_id) WHERE reemplaza_id IS NOT NULL;
CREATE INDEX idx_oci_oferta     ON oc_items (oferta_item_id) WHERE oferta_item_id IS NOT NULL;
CREATE INDEX idx_eoci_ocitem    ON entregas_oc_items (oc_item_id);
CREATE INDEX idx_cp_drog        ON compras_proveedor (drogueria_id);
CREATE INDEX idx_cp_ocitem      ON compras_proveedor (oc_item_id) WHERE oc_item_id IS NOT NULL;
CREATE INDEX idx_cp_precio_prov ON compras_proveedor (precio_proveedor_id) WHERE precio_proveedor_id IS NOT NULL;

-- drogueria_id denormalizado en las 10 tablas hijas (evita JOIN en cada política RLS)
CREATE INDEX idx_ip_drog   ON items_proceso (drogueria_id);
CREATE INDEX idx_mc_drog   ON matching_candidatos (drogueria_id);
CREATE INDEX idx_pi_drog   ON presupuesto_items (drogueria_id);
CREATE INDEX idx_oi_drog   ON ofertas_items (drogueria_id);
CREATE INDEX idx_oci_drog  ON oc_items (drogueria_id);
CREATE INDEX idx_eoc_drog  ON entregas_oc (drogueria_id);
CREATE INDEX idx_eoci_drog ON entregas_oc_items (drogueria_id);
CREATE INDEX idx_ch_drog   ON chunk_results (drogueria_id);
CREATE INDEX idx_cc_drog   ON cliente_contactos (drogueria_id);
CREATE INDEX idx_cpa_drog  ON cliente_producto_alias (drogueria_id);

-- eventos
CREATE INDEX idx_ev_drog        ON eventos (drogueria_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_ev_calendario  ON eventos (drogueria_id, fecha_programada) WHERE deleted_at IS NULL AND estado != 'cancelado';
CREATE INDEX idx_ev_pendientes  ON eventos (drogueria_id, estado, fecha_limite) WHERE deleted_at IS NULL AND estado IN ('pendiente', 'bloqueado', 'en_progreso');
CREATE INDEX idx_ev_responsable ON eventos (responsable_id, estado) WHERE deleted_at IS NULL;
CREATE INDEX idx_ev_proc        ON eventos (proceso_comercial_id) WHERE proceso_comercial_id IS NOT NULL;
CREATE INDEX idx_ev_comp        ON eventos (comparativa_id) WHERE comparativa_id IS NOT NULL;
CREATE INDEX idx_ev_oc          ON eventos (orden_compra_id) WHERE orden_compra_id IS NOT NULL;
CREATE INDEX idx_ev_cli         ON eventos (cliente_id) WHERE cliente_id IS NOT NULL;
CREATE INDEX idx_ev_prov        ON eventos (proveedor_id) WHERE proveedor_id IS NOT NULL;
CREATE INDEX idx_ev_tipo        ON eventos (drogueria_id, tipo) WHERE deleted_at IS NULL;
CREATE INDEX idx_ev_depende     ON eventos (depende_de_id) WHERE depende_de_id IS NOT NULL;
CREATE INDEX idx_ev_recurrente  ON eventos (evento_recurrente_id) WHERE evento_recurrente_id IS NOT NULL;
CREATE INDEX idx_ev_createdby   ON eventos (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_ev_updatedby   ON eventos (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_ev_deletedby   ON eventos (deleted_by) WHERE deleted_by IS NOT NULL;

-- eventos_recurrentes
CREATE INDEX idx_evr_scheduler ON eventos_recurrentes (proxima_ejecucion) WHERE activa = TRUE AND deleted_at IS NULL AND proxima_ejecucion IS NOT NULL;
CREATE INDEX idx_evr_drog      ON eventos_recurrentes (drogueria_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_evr_resp      ON eventos_recurrentes (responsable_id) WHERE responsable_id IS NOT NULL;
CREATE INDEX idx_evr_cli       ON eventos_recurrentes (cliente_id) WHERE cliente_id IS NOT NULL;
CREATE INDEX idx_evr_prov      ON eventos_recurrentes (proveedor_id) WHERE proveedor_id IS NOT NULL;
CREATE INDEX idx_evr_createdby ON eventos_recurrentes (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_evr_updatedby ON eventos_recurrentes (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_evr_deletedby ON eventos_recurrentes (deleted_by) WHERE deleted_by IS NOT NULL;

-- historial_cambios
CREATE INDEX idx_hc_proc  ON historial_cambios (proceso_comercial_id, created_at DESC) WHERE proceso_comercial_id IS NOT NULL;
CREATE INDEX idx_hc_comp  ON historial_cambios (comparativa_id, created_at DESC) WHERE comparativa_id IS NOT NULL;
CREATE INDEX idx_hc_oc    ON historial_cambios (orden_compra_id, created_at DESC) WHERE orden_compra_id IS NOT NULL;
CREATE INDEX idx_hc_pre   ON historial_cambios (presupuesto_id, created_at DESC) WHERE presupuesto_id IS NOT NULL;
CREATE INDEX idx_hc_ev    ON historial_cambios (evento_id, created_at DESC) WHERE evento_id IS NOT NULL;
CREATE INDEX idx_hc_batch ON historial_cambios (batch_id) WHERE batch_id IS NOT NULL;
CREATE INDEX idx_hc_drog  ON historial_cambios (drogueria_id, created_at DESC);
CREATE INDEX idx_hc_user  ON historial_cambios (usuario_id) WHERE usuario_id IS NOT NULL;

-- reglas_automatizacion / acciones_ejecutadas
CREATE INDEX idx_ra_vigentes    ON reglas_automatizacion (drogueria_id, entidad_objetivo, evento_disparador) WHERE activa = TRUE;
CREATE INDEX idx_ra_createdby   ON reglas_automatizacion (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_ra_updatedby   ON reglas_automatizacion (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_ev_regla       ON eventos (regla_automatizacion_id) WHERE regla_automatizacion_id IS NOT NULL;
CREATE INDEX idx_ae_drog        ON acciones_ejecutadas (drogueria_id);
CREATE INDEX idx_ae_cola        ON acciones_ejecutadas (proximo_intento_at) WHERE estado = 'pendiente';
CREATE INDEX idx_ae_metricas    ON acciones_ejecutadas (regla_id, finalizado_at) WHERE estado = 'completada';
CREATE INDEX idx_ae_proc        ON acciones_ejecutadas (proceso_comercial_id) WHERE proceso_comercial_id IS NOT NULL;
CREATE INDEX idx_ae_comp        ON acciones_ejecutadas (comparativa_id) WHERE comparativa_id IS NOT NULL;
CREATE INDEX idx_ae_oc          ON acciones_ejecutadas (orden_compra_id) WHERE orden_compra_id IS NOT NULL;
CREATE INDEX idx_ae_pre         ON acciones_ejecutadas (presupuesto_id) WHERE presupuesto_id IS NOT NULL;
CREATE INDEX idx_ae_ev          ON acciones_ejecutadas (evento_id) WHERE evento_id IS NOT NULL;

-- proveedor_producto_alias
CREATE INDEX idx_ppa_busqueda   ON proveedor_producto_alias (proveedor_id, descripcion_normalizada) WHERE vigente = TRUE;
CREATE INDEX idx_ppa_producto   ON proveedor_producto_alias (producto_id);
CREATE INDEX idx_ppa_drog       ON proveedor_producto_alias (drogueria_id);
CREATE INDEX idx_ppa_creadopor  ON proveedor_producto_alias (creado_por) WHERE creado_por IS NOT NULL;

-- productos.clasificacion
CREATE INDEX idx_prod_clasificacion ON productos (drogueria_id, clasificacion) WHERE deleted_at IS NULL;

-- índices parciales de soft delete en entidades de negocio
CREATE INDEX idx_cli_activos  ON clientes (drogueria_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_prod_activos ON productos (drogueria_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_prov_activos ON proveedores (drogueria_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_proc_activos ON procesos_comerciales (drogueria_id, estado) WHERE deleted_at IS NULL;
CREATE INDEX idx_pre_activos  ON presupuestos (drogueria_id, estado) WHERE deleted_at IS NULL;
CREATE INDEX idx_comp_activos ON comparativas (drogueria_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_oc_activos   ON ordenes_compra (drogueria_id, estado) WHERE deleted_at IS NULL;

-- FKs de auditoría (*_by / *_por) en entidades de negocio
CREATE INDEX idx_cli_createdby   ON clientes (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_cli_updatedby   ON clientes (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_cli_deletedby   ON clientes (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_prod_createdby  ON productos (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_prod_updatedby  ON productos (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_prod_deletedby  ON productos (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_prov_createdby  ON proveedores (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_prov_updatedby  ON proveedores (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_prov_deletedby  ON proveedores (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_proc_createdby  ON procesos_comerciales (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_proc_updatedby  ON procesos_comerciales (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_proc_deletedby  ON procesos_comerciales (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_pre_createdby   ON presupuestos (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_pre_updatedby   ON presupuestos (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_pre_deletedby   ON presupuestos (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_comp_createdby  ON comparativas (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_comp_updatedby  ON comparativas (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_comp_deletedby  ON comparativas (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_oc_createdby    ON ordenes_compra (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_oc_updatedby    ON ordenes_compra (updated_by) WHERE updated_by IS NOT NULL;
CREATE INDEX idx_oc_deletedby    ON ordenes_compra (deleted_by) WHERE deleted_by IS NOT NULL;
CREATE INDEX idx_cobs_creadopor  ON cliente_observaciones (creado_por) WHERE creado_por IS NOT NULL;
CREATE INDEX idx_cfmt_actualiz   ON cliente_formato_documentos (actualizado_por) WHERE actualizado_por IS NOT NULL;
CREATE INDEX idx_alias_creadopor ON cliente_producto_alias (creado_por) WHERE creado_por IS NOT NULL;
CREATE INDEX idx_pp_creadopor    ON precios_proveedor (creado_por) WHERE creado_por IS NOT NULL;
CREATE INDEX idx_er_validadopor  ON extraction_results (validado_por) WHERE validado_por IS NOT NULL;
CREATE INDEX idx_pre_aprobadopor ON presupuestos (aprobado_por) WHERE aprobado_por IS NOT NULL;
CREATE INDEX idx_pre_presentapor ON presupuestos (presentado_por) WHERE presentado_por IS NOT NULL;
CREATE INDEX idx_pi_ajustadopor  ON presupuesto_items (precio_ajustado_por) WHERE precio_ajustado_por IS NOT NULL;
CREATE INDEX idx_cp_creadopor    ON compras_proveedor (creado_por) WHERE creado_por IS NOT NULL;

-- notificaciones
CREATE INDEX idx_no_no_leidas ON notificaciones (destinatario_id, created_at DESC) WHERE leida_at IS NULL AND archivada_at IS NULL;
CREATE INDEX idx_no_dest      ON notificaciones (destinatario_id, created_at DESC);
CREATE INDEX idx_no_drog      ON notificaciones (drogueria_id, created_at DESC);
CREATE INDEX idx_no_proc      ON notificaciones (proceso_comercial_id) WHERE proceso_comercial_id IS NOT NULL;
CREATE INDEX idx_no_comp      ON notificaciones (comparativa_id) WHERE comparativa_id IS NOT NULL;
CREATE INDEX idx_no_oc        ON notificaciones (orden_compra_id) WHERE orden_compra_id IS NOT NULL;
CREATE INDEX idx_no_pre       ON notificaciones (presupuesto_id) WHERE presupuesto_id IS NOT NULL;
CREATE INDEX idx_no_ev        ON notificaciones (evento_id) WHERE evento_id IS NOT NULL;
CREATE INDEX idx_no_accion    ON notificaciones (accion_ejecutada_id) WHERE accion_ejecutada_id IS NOT NULL;
CREATE INDEX idx_ne_cola      ON notificacion_entregas (canal, created_at) WHERE estado = 'pendiente';
CREATE INDEX idx_ne_notif     ON notificacion_entregas (notificacion_id);
CREATE INDEX idx_ne_drog      ON notificacion_entregas (drogueria_id);
CREATE INDEX idx_np_user      ON notificacion_preferencias (usuario_id);
CREATE INDEX idx_np_drog      ON notificacion_preferencias (drogueria_id);


-- =============================================================================
-- TRIGGERS updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER t_u_drog   BEFORE UPDATE ON droguerias                 FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_cli    BEFORE UPDATE ON clientes                   FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_cc     BEFORE UPDATE ON cliente_contactos          FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_cfmt   BEFORE UPDATE ON cliente_formato_documentos FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_prov   BEFORE UPDATE ON proveedores                FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_prod   BEFORE UPDATE ON productos                  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_stock  BEFORE UPDATE ON stock_productos            FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_alias  BEFORE UPDATE ON cliente_producto_alias     FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_pp     BEFORE UPDATE ON precios_proveedor          FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_proc   BEFORE UPDATE ON procesos_comerciales       FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_ps     BEFORE UPDATE ON processing_sessions        FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_er     BEFORE UPDATE ON extraction_results         FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_ip     BEFORE UPDATE ON items_proceso              FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_rp     BEFORE UPDATE ON reglas_pricing             FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_pre    BEFORE UPDATE ON presupuestos               FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_pi     BEFORE UPDATE ON presupuesto_items          FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_comp   BEFORE UPDATE ON comparativas               FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_oc     BEFORE UPDATE ON ordenes_compra             FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_eoc    BEFORE UPDATE ON entregas_oc                FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_eventos BEFORE UPDATE ON eventos                   FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_evr    BEFORE UPDATE ON eventos_recurrentes        FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_ra     BEFORE UPDATE ON reglas_automatizacion      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_ppa    BEFORE UPDATE ON proveedor_producto_alias   FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_u_np     BEFORE UPDATE ON notificacion_preferencias  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
-- historial_cambios, acciones_ejecutadas, notificaciones, notificacion_entregas:
-- sin trigger, no tienen columna updated_at (son tablas append/log, no de estado editable)


-- =============================================================================
-- VISTAS
-- =============================================================================

-- Insumo clave del motor: precio ganador histórico por producto
CREATE VIEW v_precio_mercado_producto AS
SELECT
    ip.producto_id,
    c.drogueria_id,
    COUNT(*)                          AS muestras,
    MIN(oi.precio_unitario)           AS precio_min,
    MAX(oi.precio_unitario)           AS precio_max,
    ROUND(AVG(oi.precio_unitario), 2) AS precio_promedio,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY oi.precio_unitario) AS precio_mediana,
    MAX(c.created_at)                 AS ultima_muestra
FROM ofertas_items oi
JOIN comparativas c   ON c.id = oi.comparativa_id AND c.es_vigente = TRUE
JOIN items_proceso ip ON ip.id = oi.item_proceso_id
WHERE ip.producto_id IS NOT NULL
  AND (oi.adjudicada OR oi.adjudicacion_estimada)
GROUP BY ip.producto_id, c.drogueria_id;

-- Pantalla de aprobación del presupuesto
CREATE VIEW v_presupuesto_revision AS
SELECT
    p.id                        AS presupuesto_id,
    p.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    cl.nombre                   AS cliente,
    p.estado,
    pi.id                       AS presupuesto_item_id,
    ip.numero_renglon,
    ip.descripcion,
    ip.cantidad                 AS cantidad_solicitada,
    prod.nombre                 AS producto,
    pi.precio_unitario,
    pi.cantidad_ofertada,
    pi.monto_total,
    pi.metodo_precio,
    pi.costo_usado,
    pi.origen_costo,
    pi.precio_mercado_usado,
    pi.margen_resultante_pct,
    pi.stock_verificado,
    pi.stock_al_generar,
    pi.excluido,
    pi.motivo_exclusion,
    (pi.precio_ajustado_por IS NOT NULL) AS ajustado_por_humano,
    COALESCE(prov.nombre_comercial, prov.razon_social) AS proveedor_compra,
    COALESCE(pp.plazo_pago_dias, prov.plazo_pago_dias) AS plazo_pago_proveedor,
    cl.plazo_pago_dias          AS plazo_pago_cliente,
    pi.mantenimiento_hasta_usado,
    (pi.mantenimiento_hasta_usado IS NOT NULL
     AND proc.vencimiento IS NOT NULL
     AND pi.mantenimiento_hasta_usado < proc.vencimiento) AS alerta_mantenimiento
FROM presupuestos p
JOIN procesos_comerciales proc ON proc.id = p.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
JOIN presupuesto_items pi      ON pi.presupuesto_id = p.id
JOIN items_proceso ip          ON ip.id = pi.item_proceso_id
LEFT JOIN productos prod       ON prod.id = pi.producto_id
LEFT JOIN precios_proveedor pp ON pp.id = pi.precio_proveedor_id
LEFT JOIN proveedores prov     ON prov.id = pp.proveedor_id
ORDER BY p.id, ip.numero_renglon;

-- Cola de matching pendiente
CREATE VIEW v_matching_pendiente AS
SELECT
    ip.id                       AS item_proceso_id,
    ip.proceso_comercial_id,
    proc.nombre                 AS proceso,
    proc.clase,
    proc.cliente_id,
    cl.nombre                   AS cliente,
    ip.numero_renglon,
    ip.descripcion,
    ip.estado_matching,
    ip.confianza_matching,
    (SELECT COUNT(*) FROM matching_candidatos mc WHERE mc.item_proceso_id = ip.id) AS candidatos
FROM items_proceso ip
JOIN procesos_comerciales proc ON proc.id = ip.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
WHERE ip.estado_matching IN ('pendiente', 'sugerido')
  AND proc.estado IN ('abierto', 'presupuestado')
ORDER BY proc.vencimiento NULLS FIRST, ip.numero_renglon;

-- Precios especiales vigentes (costo alternativo del motor)
CREATE VIEW v_precios_especiales_vigentes AS
SELECT
    pp.id                       AS precio_proveedor_id,
    pp.drogueria_id,
    pp.producto_id,
    prod.nombre                 AS producto,
    pp.item_proceso_id,
    pp.precio_unitario,
    pp.cantidad_minima,
    pp.cantidad_maxima,
    COALESCE(prov.nombre_comercial, prov.razon_social) AS proveedor,
    COALESCE(pp.plazo_pago_dias, prov.plazo_pago_dias) AS plazo_pago_dias,
    pp.mantenimiento_hasta,
    pp.mantenimiento_hasta - CURRENT_DATE AS dias_restantes
FROM precios_proveedor pp
JOIN proveedores prov ON prov.id = pp.proveedor_id
JOIN productos prod   ON prod.id = pp.producto_id
WHERE pp.activa = TRUE AND pp.mantenimiento_hasta >= CURRENT_DATE
ORDER BY pp.producto_id, pp.precio_unitario;

-- Renglones ganados (oficial o estimado) para anticipar compras
CREATE VIEW v_renglones_ganados AS
SELECT
    c.proceso_comercial_id,
    proc.nombre                 AS proceso,
    cl.nombre                   AS cliente,
    oi.id                       AS oferta_item_id,
    oi.renglon_id,
    oi.descripcion,
    oi.precio_unitario,
    oi.cantidad_ofertada,
    oi.adjudicada               AS ganado_oficial,
    oi.adjudicacion_estimada    AS ganado_estimado,
    CASE WHEN oi.adjudicada THEN 'oficial'
         WHEN oi.adjudicacion_estimada THEN 'estimado' END AS nivel
FROM ofertas_items oi
JOIN comparativas c            ON c.id = oi.comparativa_id AND c.es_vigente = TRUE
JOIN procesos_comerciales proc ON proc.id = c.proceso_comercial_id
LEFT JOIN clientes cl          ON cl.id = proc.cliente_id
WHERE oi.es_drogueria_propia = TRUE
  AND (oi.adjudicada OR oi.adjudicacion_estimada);

-- Entregas pendientes con atraso
CREATE VIEW v_entregas_pendientes AS
SELECT
    oc.numero_oc,
    cl.nombre AS cliente,
    e.numero_entrega,
    e.fecha_entrega_planificada,
    e.estado,
    CURRENT_DATE - e.fecha_entrega_planificada AS dias_atraso
FROM entregas_oc e
JOIN ordenes_compra oc ON oc.id = e.orden_compra_id
LEFT JOIN clientes cl  ON cl.id = oc.cliente_id
WHERE e.estado NOT IN ('entregada', 'rechazada');

-- Proveedores sin matchear
CREATE VIEW v_ofertas_sin_matchear AS
SELECT
    oi.proveedor AS texto_crudo,
    c.drogueria_id,
    COUNT(*)     AS apariciones,
    COUNT(*) FILTER (WHERE oi.adjudicada) AS veces_ganador
FROM ofertas_items oi
JOIN comparativas c ON c.id = oi.comparativa_id
WHERE oi.proveedor_id IS NULL AND oi.es_drogueria_propia = FALSE
GROUP BY oi.proveedor, c.drogueria_id
ORDER BY apariciones DESC;

-- Instrucciones de formato para el prompt
CREATE VIEW v_formato_para_prompt AS
SELECT
    cf.cliente_id,
    cl.nombre AS cliente,
    cf.doc_type,
    cf.instrucciones_prompt,
    cf.archivo_ejemplo_path
FROM cliente_formato_documentos cf
JOIN clientes cl ON cl.id = cf.cliente_id
WHERE cf.activo = TRUE AND cf.instrucciones_prompt IS NOT NULL;

-- Comparación: precio especial cotizado vs precio real de compra
CREATE VIEW v_compras_vs_cotizado AS
SELECT
    cp.id                       AS compra_id,
    prod.nombre                 AS producto,
    COALESCE(prov.nombre_comercial, prov.razon_social) AS proveedor,
    cp.cantidad,
    cp.precio_unitario          AS precio_compra_real,
    pp.precio_unitario          AS precio_cotizado,
    cp.precio_unitario - pp.precio_unitario AS diferencia,
    cp.fecha_compra,
    pp.mantenimiento_hasta,
    (cp.fecha_compra > pp.mantenimiento_hasta) AS comprado_fuera_de_mantenimiento
FROM compras_proveedor cp
JOIN productos prod            ON prod.id = cp.producto_id
JOIN proveedores prov          ON prov.id = cp.proveedor_id
LEFT JOIN precios_proveedor pp ON pp.id = cp.precio_proveedor_id
WHERE cp.precio_proveedor_id IS NOT NULL;

COMMENT ON VIEW v_compras_vs_cotizado IS 'Compara el precio que el proveedor cotizó vs lo que efectivamente cobró al comprar. comprado_fuera_de_mantenimiento = TRUE indica que se compró después de vencida la oferta (riesgo de sobreprecio).';

-- Eventos con su situación de bloqueo resuelta (dependencia lineal, autoreferencia)
CREATE VIEW v_eventos_bloqueo AS
SELECT
    e.id                AS evento_id,
    e.drogueria_id,
    e.tipo,
    e.titulo,
    e.estado,
    e.prioridad,
    e.fecha_limite,
    e.responsable_id,
    e.depende_de_id,
    dep.titulo          AS depende_de,
    dep.estado          AS estado_dependencia,
    (e.depende_de_id IS NULL OR dep.estado = 'completado') AS puede_avanzar
FROM eventos e
LEFT JOIN eventos dep ON dep.id = e.depende_de_id AND dep.deleted_at IS NULL
WHERE e.deleted_at IS NULL;

COMMENT ON VIEW v_eventos_bloqueo IS 'puede_avanzar=TRUE cuando el evento no depende de nadie, o su dependencia ya está completada. El backend lo usa para desbloquear eventos automáticamente.';

-- Rendimiento de las automatizaciones
CREATE VIEW v_metricas_automatizacion AS
SELECT
    r.id                                                AS regla_id,
    r.drogueria_id,
    r.nombre,
    r.tipo_accion,
    r.modo_ejecucion,
    COUNT(a.id)                                         AS ejecuciones,
    COUNT(a.id) FILTER (WHERE a.estado = 'completada')  AS exitosas,
    COUNT(a.id) FILTER (WHERE a.estado = 'fallida')     AS fallidas,
    ROUND(AVG(a.duracion_ms) FILTER (WHERE a.estado = 'completada'), 0) AS duracion_promedio_ms,
    MAX(a.duracion_ms) FILTER (WHERE a.estado = 'completada')           AS duracion_max_ms,
    ROUND(AVG(a.intentos), 2)                           AS intentos_promedio,
    MAX(a.finalizado_at)                                AS ultima_ejecucion
FROM reglas_automatizacion r
LEFT JOIN acciones_ejecutadas a ON a.regla_id = r.id
GROUP BY r.id, r.drogueria_id, r.nombre, r.tipo_accion, r.modo_ejecucion;

COMMENT ON VIEW v_metricas_automatizacion IS 'Rendimiento por regla: cuánto tarda, cuántas veces falla, cuántos reintentos necesita. Base para medir agentes de IA.';


-- =============================================================================
-- SECURITY INVOKER — obligatorio en vistas dentro de un sistema con RLS
-- Sin esto, las vistas corren con los privilegios de quien las creó (owner)
-- en vez de aplicar el RLS del usuario que consulta.
-- =============================================================================

ALTER VIEW v_precio_mercado_producto     SET (security_invoker = on);
ALTER VIEW v_presupuesto_revision        SET (security_invoker = on);
ALTER VIEW v_matching_pendiente          SET (security_invoker = on);
ALTER VIEW v_precios_especiales_vigentes SET (security_invoker = on);
ALTER VIEW v_renglones_ganados           SET (security_invoker = on);
ALTER VIEW v_entregas_pendientes         SET (security_invoker = on);
ALTER VIEW v_ofertas_sin_matchear        SET (security_invoker = on);
ALTER VIEW v_formato_para_prompt         SET (security_invoker = on);
ALTER VIEW v_compras_vs_cotizado         SET (security_invoker = on);
ALTER VIEW v_eventos_bloqueo             SET (security_invoker = on);
ALTER VIEW v_metricas_automatizacion     SET (security_invoker = on);
