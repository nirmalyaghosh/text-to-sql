-- ============================================
-- MANUFACTURING & E-COMMERCE SCHEMA
-- ============================================
-- Schema for Text-to-SQL Blog Series
-- PostgreSQL version
-- Total: 35 tables across 7 domains
-- Created: 2025-02-06
-- ============================================

-- ============================================
-- DROP ALL TABLES (CASCADE handles dependencies)
-- ============================================

DROP TABLE IF EXISTS customs_documentation CASCADE;
DROP TABLE IF EXISTS shipments CASCADE;
DROP TABLE IF EXISTS shipping_routes CASCADE;
DROP TABLE IF EXISTS delivery_partners CASCADE;
DROP TABLE IF EXISTS obsolete_inventory CASCADE;
DROP TABLE IF EXISTS stock_reconciliation CASCADE;
DROP TABLE IF EXISTS inventory_valuation CASCADE;
DROP TABLE IF EXISTS safety_stock_levels CASCADE;
DROP TABLE IF EXISTS inventory_transactions CASCADE;
DROP TABLE IF EXISTS raw_material_inventory CASCADE;
DROP TABLE IF EXISTS finished_goods_inventory CASCADE;
DROP TABLE IF EXISTS returns CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS profitability_analysis CASCADE;
DROP TABLE IF EXISTS cost_allocations CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS demand_forecasts CASCADE;
DROP TABLE IF EXISTS customer_lifetime_value CASCADE;
DROP TABLE IF EXISTS conversion_funnels CASCADE;
DROP TABLE IF EXISTS campaigns CASCADE;
DROP TABLE IF EXISTS website_sessions CASCADE;
DROP TABLE IF EXISTS departments CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS warehouses CASCADE;
DROP TABLE IF EXISTS quality_inspections CASCADE;
DROP TABLE IF EXISTS production_runs CASCADE;
DROP TABLE IF EXISTS production_lines CASCADE;
DROP TABLE IF EXISTS bill_of_materials CASCADE;
DROP TABLE IF EXISTS raw_materials CASCADE;
DROP TABLE IF EXISTS suppliers CASCADE;
DROP TABLE IF EXISTS product_variants CASCADE;
DROP TABLE IF EXISTS products CASCADE;

DROP VIEW IF EXISTS vw_available_inventory CASCADE;
DROP VIEW IF EXISTS vw_order_fulfillment_status CASCADE;

-- DOMAIN 1: MANUFACTURING (8 tables)
-- ============================================

CREATE TABLE products (
    product_id VARCHAR(20) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    manufacturing_cost DECIMAL(10,2) CHECK (manufacturing_cost >= 0),
    weight_kg DECIMAL(6,2) CHECK (weight_kg >= 0),
    geo_segments JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    discontinued_date DATE
);

CREATE INDEX idx_products_category ON products(category);

COMMENT ON TABLE products IS 'Base product catalog with geographic restrictions';

CREATE TABLE product_variants (
    variant_id VARCHAR(25) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    sku VARCHAR(30) UNIQUE NOT NULL,
    size VARCHAR(20),
    color VARCHAR(30),
    regional_specs JSONB,
    price_adjustment DECIMAL(10,2) DEFAULT 0.00,

    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE INDEX idx_product_variant ON product_variants(product_id, variant_id);
CREATE INDEX idx_product_variants_sku ON product_variants(sku);

COMMENT ON TABLE product_variants IS 'Product variations for different markets';

CREATE TABLE suppliers (
    supplier_id VARCHAR(20) PRIMARY KEY,
    supplier_name VARCHAR(100) NOT NULL,
    country VARCHAR(50) NOT NULL,
    reliability_score DECIMAL(3,2) CHECK (reliability_score BETWEEN 0 AND 1),
    avg_lead_time_days INTEGER CHECK (avg_lead_time_days >= 0),
    payment_terms VARCHAR(20)
);

CREATE INDEX idx_country_reliability ON suppliers(country, reliability_score);

COMMENT ON TABLE suppliers IS 'Raw material suppliers with performance metrics';

CREATE TABLE raw_materials (
    material_id VARCHAR(20) PRIMARY KEY,
    material_name VARCHAR(100) NOT NULL,
    supplier_id VARCHAR(20) NOT NULL,
    unit_cost DECIMAL(10,4) CHECK (unit_cost >= 0),
    unit_of_measure VARCHAR(10) NOT NULL,
    lead_time_days INTEGER CHECK (lead_time_days >= 0),
    min_order_quantity INTEGER CHECK (min_order_quantity > 0),

    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE INDEX idx_supplier_material ON raw_materials(supplier_id, material_id);

COMMENT ON TABLE raw_materials IS 'Raw materials for manufacturing';

CREATE TABLE bill_of_materials (
    bom_id VARCHAR(30) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    material_id VARCHAR(20) NOT NULL,
    quantity_required DECIMAL(8,3) CHECK (quantity_required > 0),
    scrap_factor DECIMAL(5,4) DEFAULT 0.05 CHECK (scrap_factor BETWEEN 0 AND 1),
    level INTEGER DEFAULT 1 CHECK (level >= 1),

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (material_id) REFERENCES raw_materials(material_id),
    UNIQUE (product_id, material_id)
);

CREATE INDEX idx_product_level ON bill_of_materials(product_id, level);

COMMENT ON TABLE bill_of_materials IS 'Multi-level bill of materials for products';

CREATE TABLE production_lines (
    line_id VARCHAR(20) PRIMARY KEY,
    line_name VARCHAR(50) NOT NULL,
    location VARCHAR(50) NOT NULL,
    capacity_per_hour INTEGER CHECK (capacity_per_hour > 0),
    maintenance_schedule JSONB,
    status VARCHAR(20) DEFAULT 'active',
    primary_product_category VARCHAR(50)
);

CREATE INDEX idx_location_status ON production_lines(location, status);

COMMENT ON TABLE production_lines IS 'Manufacturing production lines';

CREATE TABLE production_runs (
    run_id VARCHAR(30) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    quantity INTEGER CHECK (quantity > 0),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'in_progress', 'completed', 'cancelled')),
    production_line_id VARCHAR(20) NOT NULL,
    defects_count INTEGER DEFAULT 0 CHECK (defects_count >= 0),
    yield_percentage DECIMAL(5,2) GENERATED ALWAYS
        AS (CASE WHEN quantity > 0 THEN (quantity - defects_count) * 100.0 / quantity ELSE 0 END) STORED,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    FOREIGN KEY (production_line_id) REFERENCES production_lines(line_id),
    CHECK (end_time IS NULL OR start_time <= end_time)
);

CREATE INDEX idx_run_status_time ON production_runs(status, start_time);
CREATE INDEX idx_product_line ON production_runs(product_id, production_line_id);

COMMENT ON TABLE production_runs IS 'Manufacturing batch production runs';

CREATE TABLE quality_inspections (
    inspection_id VARCHAR(30) PRIMARY KEY,
    run_id VARCHAR(30) NOT NULL,
    inspector_id VARCHAR(20) NOT NULL,
    passed BOOLEAN NOT NULL,
    defects JSONB,
    inspection_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,

    FOREIGN KEY (run_id) REFERENCES production_runs(run_id)
);

CREATE INDEX idx_run_inspection ON quality_inspections(run_id, inspection_time);
CREATE INDEX idx_passed_inspections ON quality_inspections(passed, inspection_time);

COMMENT ON TABLE quality_inspections IS 'Quality inspection records for production runs';

-- DOMAIN 2: INVENTORY MANAGEMENT (7 tables)
-- ============================================

CREATE TABLE finished_goods_inventory (
    inventory_id VARCHAR(30) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    quantity INTEGER CHECK (quantity >= 0),
    allocated_quantity INTEGER DEFAULT 0 CHECK (allocated_quantity >= 0),
    available_quantity INTEGER GENERATED ALWAYS AS (quantity - allocated_quantity) STORED,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    batch_number VARCHAR(50),

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    CHECK (allocated_quantity <= quantity)
);

CREATE INDEX idx_available_product ON finished_goods_inventory(product_id, available_quantity);
CREATE INDEX idx_warehouse_product ON finished_goods_inventory(warehouse_id, product_id, variant_id);
CREATE INDEX idx_batch_inventory ON finished_goods_inventory(batch_number);

COMMENT ON TABLE finished_goods_inventory IS 'Finished goods inventory across warehouses';

CREATE TABLE raw_material_inventory (
    inventory_id VARCHAR(30) PRIMARY KEY,
    material_id VARCHAR(20) NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    quantity DECIMAL(10,3) CHECK (quantity >= 0),
    allocated_quantity DECIMAL(10,3) DEFAULT 0 CHECK (allocated_quantity >= 0),
    unit_of_measure VARCHAR(10) NOT NULL,
    received_date DATE NOT NULL,
    expiry_date DATE,
    supplier_batch VARCHAR(50),

    FOREIGN KEY (material_id) REFERENCES raw_materials(material_id),
    CHECK (allocated_quantity <= quantity)
);

CREATE INDEX idx_material_warehouse ON raw_material_inventory(material_id, warehouse_id);
CREATE INDEX idx_expiry_date ON raw_material_inventory(expiry_date) WHERE expiry_date IS NOT NULL;

COMMENT ON TABLE raw_material_inventory IS 'Raw material inventory with expiry tracking';

CREATE TABLE inventory_transactions (
    transaction_id VARCHAR(40) PRIMARY KEY,
    transaction_type VARCHAR(20) NOT NULL
        CHECK (transaction_type IN ('RECEIPT', 'ISSUE', 'TRANSFER', 'ADJUSTMENT', 'ALLOCATION')),
    inventory_type VARCHAR(20) NOT NULL
        CHECK (inventory_type IN ('FINISHED_GOODS', 'RAW_MATERIAL')),
    inventory_id VARCHAR(30) NOT NULL,
    quantity_change DECIMAL(10,3) NOT NULL,
    reference_id VARCHAR(50),
    transaction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    performed_by VARCHAR(20) NOT NULL,
    notes TEXT
);

CREATE INDEX idx_transaction_time ON inventory_transactions(transaction_time);
CREATE INDEX idx_inventory_transactions ON inventory_transactions(inventory_type, inventory_id, transaction_time);
CREATE INDEX idx_reference_transactions ON inventory_transactions(reference_id, transaction_type);

COMMENT ON TABLE inventory_transactions IS 'Audit trail for all inventory movements';

CREATE TABLE safety_stock_levels (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    safety_stock_quantity INTEGER CHECK (safety_stock_quantity >= 0),
    reorder_point INTEGER CHECK (reorder_point >= 0),
    calculation_method VARCHAR(30),
    service_level_target DECIMAL(4,3) DEFAULT 0.95 CHECK (service_level_target BETWEEN 0 AND 1),
    last_calculated DATE DEFAULT CURRENT_DATE,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    UNIQUE (product_id, variant_id, warehouse_id)
);

CREATE INDEX idx_reorder_alerts ON safety_stock_levels(warehouse_id, product_id, variant_id);

COMMENT ON TABLE safety_stock_levels IS 'Safety stock calculations and reorder points';

CREATE TABLE inventory_valuation (
    valuation_id VARCHAR(40) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    valuation_method VARCHAR(10) NOT NULL
        CHECK (valuation_method IN ('FIFO', 'LIFO', 'WAC')),
    unit_value DECIMAL(12,4) CHECK (unit_value >= 0),
    total_value DECIMAL(15,2) CHECK (total_value >= 0),
    as_of_date DATE NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    valuation_basis VARCHAR(30)
        CHECK (valuation_basis IN ('cost', 'market', 'lower_of_cost_or_market')),

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    UNIQUE (product_id, as_of_date, valuation_method)
);

CREATE INDEX idx_valuation_date ON inventory_valuation(as_of_date, product_id);

COMMENT ON TABLE inventory_valuation IS 'Financial valuation of inventory';

CREATE TABLE stock_reconciliation (
    reconciliation_id VARCHAR(40) PRIMARY KEY,
    warehouse_id VARCHAR(20) NOT NULL,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    expected_quantity INTEGER CHECK (expected_quantity >= 0),
    actual_quantity INTEGER CHECK (actual_quantity >= 0),
    discrepancy_amount INTEGER GENERATED ALWAYS AS (actual_quantity - expected_quantity) STORED,
    discrepancy_reason VARCHAR(100),
    reconciled_by VARCHAR(20) NOT NULL,
    reconciled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id)
);

CREATE INDEX idx_reconciliation_date ON stock_reconciliation(reconciled_at);
CREATE INDEX idx_discrepancy_analysis ON stock_reconciliation(warehouse_id, ABS(discrepancy_amount));

COMMENT ON TABLE stock_reconciliation IS 'Physical vs system inventory reconciliation';

CREATE TABLE obsolete_inventory (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    quantity INTEGER CHECK (quantity >= 0),
    write_off_value DECIMAL(15,2) CHECK (write_off_value >= 0),
    reason VARCHAR(100)
        CHECK (reason IN ('damaged', 'expired', 'discontinued', 'excess')),
    disposition VARCHAR(20)
        CHECK (disposition IN ('destroy', 'donate', 'discount', 'recycle')),
    recorded_by VARCHAR(20) NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id)
);

CREATE INDEX idx_obsolete_reason_date ON obsolete_inventory(reason, recorded_at);
CREATE INDEX idx_disposition_tracking ON obsolete_inventory(disposition, warehouse_id);

COMMENT ON TABLE obsolete_inventory IS 'Inventory marked for write-off and disposition';

-- DOMAIN 3: LOGISTICS (5 tables)
-- ============================================

CREATE TABLE warehouses (
    warehouse_id VARCHAR(20) PRIMARY KEY,
    warehouse_name VARCHAR(100) NOT NULL,
    location VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL
        CHECK (type IN ('central', 'regional', 'local', 'popup')),
    capacity_sqft INTEGER CHECK (capacity_sqft > 0),
    country VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    manager_id VARCHAR(20) NOT NULL,
    operational_hours JSONB
);

CREATE INDEX idx_warehouse_region ON warehouses(country, region, type);
CREATE INDEX idx_manager_warehouses ON warehouses(manager_id);

COMMENT ON TABLE warehouses IS 'Warehouse network across regions';

CREATE TABLE delivery_partners (
    partner_id VARCHAR(20) PRIMARY KEY,
    partner_name VARCHAR(100) NOT NULL,
    service_type VARCHAR(30) NOT NULL
        CHECK (service_type IN ('standard', 'express', 'freight', 'last_mile')),
    coverage_countries JSONB,
    performance_score DECIMAL(3,2) DEFAULT 1.0 CHECK (performance_score BETWEEN 0 AND 1),
    contract_start_date DATE NOT NULL,
    contract_end_date DATE NOT NULL,
    rate_card JSONB,

    CHECK (contract_end_date > contract_start_date)
);

CREATE INDEX idx_partner_performance ON delivery_partners(performance_score, service_type);
CREATE INDEX idx_contract_dates ON delivery_partners(contract_start_date, contract_end_date);

COMMENT ON TABLE delivery_partners IS 'Logistics and delivery service partners';

CREATE TABLE shipping_routes (
    route_id VARCHAR(30) PRIMARY KEY,
    from_warehouse_id VARCHAR(20) NOT NULL,
    to_warehouse_id VARCHAR(20) NOT NULL,
    distance_km INTEGER CHECK (distance_km >= 0),
    estimated_days INTEGER CHECK (estimated_days >= 0),
    cost_per_kg DECIMAL(8,2) CHECK (cost_per_kg >= 0),
    carrier_id VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    customs_required BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (from_warehouse_id) REFERENCES warehouses(warehouse_id),
    FOREIGN KEY (to_warehouse_id) REFERENCES warehouses(warehouse_id),
    FOREIGN KEY (carrier_id) REFERENCES delivery_partners(partner_id),
    CHECK (from_warehouse_id != to_warehouse_id),
    UNIQUE (from_warehouse_id, to_warehouse_id, carrier_id)
);

CREATE INDEX idx_active_routes ON shipping_routes(is_active, from_warehouse_id, to_warehouse_id);

COMMENT ON TABLE shipping_routes IS 'Shipping routes between warehouses';

CREATE TABLE shipments (
    shipment_id VARCHAR(40) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    from_warehouse_id VARCHAR(20) NOT NULL,
    to_customer_id VARCHAR(20) NOT NULL,
    partner_id VARCHAR(20) NOT NULL,
    status VARCHAR(30) DEFAULT 'pending'
        CHECK (status IN ('pending', 'picked', 'in_transit', 'delivered', 'delayed', 'cancelled')),
    shipped_at TIMESTAMP,
    estimated_delivery DATE,
    actual_delivery TIMESTAMP NULL,
    tracking_number VARCHAR(100),
    shipping_cost DECIMAL(10,2) CHECK (shipping_cost >= 0),

    FOREIGN KEY (from_warehouse_id) REFERENCES warehouses(warehouse_id),
    FOREIGN KEY (partner_id) REFERENCES delivery_partners(partner_id),
    CHECK (actual_delivery IS NULL OR shipped_at <= actual_delivery)
);

CREATE INDEX idx_shipment_status ON shipments(status, shipped_at);
CREATE INDEX idx_customer_shipments ON shipments(to_customer_id, shipped_at);
CREATE INDEX idx_tracking ON shipments(tracking_number);

COMMENT ON TABLE shipments IS 'Shipment tracking for customer orders';

CREATE TABLE customs_documentation (
    customs_id VARCHAR(40) PRIMARY KEY,
    shipment_id VARCHAR(40) NOT NULL,
    document_type VARCHAR(30) NOT NULL
        CHECK (document_type IN ('commercial_invoice', 'packing_list', 'certificate_of_origin')),
    document_url VARCHAR(500),
    hs_code VARCHAR(12),
    declared_value DECIMAL(12,2) CHECK (declared_value >= 0),
    duties_paid DECIMAL(10,2) CHECK (duties_paid >= 0),
    verified BOOLEAN DEFAULT FALSE,
    verified_by VARCHAR(20),
    verified_at TIMESTAMP,

    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

CREATE INDEX idx_shipment_docs ON customs_documentation(shipment_id, document_type);
CREATE INDEX idx_verification_status ON customs_documentation(verified, verified_at);

COMMENT ON TABLE customs_documentation IS 'Customs documentation for international shipments';

-- DOMAIN 4: E-COMMERCE (4 tables)
-- ============================================

CREATE TABLE customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(30),
    country VARCHAR(50) NOT NULL,
    customer_segment VARCHAR(30) NOT NULL
        CHECK (customer_segment IN ('retail', 'wholesale', 'corporate')),
    acquisition_channel VARCHAR(30),
    lifetime_value DECIMAL(12,2) DEFAULT 0.00 CHECK (lifetime_value >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_customer_segment ON customers(customer_segment, country);
CREATE INDEX idx_lifetime_value ON customers(lifetime_value DESC);
CREATE INDEX idx_acquisition ON customers(acquisition_channel, created_at);

COMMENT ON TABLE customers IS 'Customer master data with segmentation';

CREATE TABLE orders (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(20) NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(12,2) CHECK (total_amount >= 0),
    status VARCHAR(30) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled', 'returned')),
    currency VARCHAR(3) DEFAULT 'USD',
    shipping_address JSONB,
    billing_address JSONB,
    payment_method VARCHAR(30),
    fulfillment_priority VARCHAR(20) DEFAULT 'standard'
        CHECK (fulfillment_priority IN ('standard', 'express', 'scheduled')),

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE INDEX idx_order_date_customer ON orders(order_date DESC, customer_id);
CREATE INDEX idx_order_status ON orders(status, order_date);
CREATE INDEX idx_customer_orders ON orders(customer_id, order_date DESC);

COMMENT ON TABLE orders IS 'Customer orders with fulfillment tracking';

CREATE TABLE order_items (
    order_item_id VARCHAR(40) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    quantity INTEGER CHECK (quantity > 0),
    unit_price DECIMAL(10,2) CHECK (unit_price >= 0),
    discount DECIMAL(10,2) DEFAULT 0.00 CHECK (discount >= 0),
    tax DECIMAL(10,2) DEFAULT 0.00 CHECK (tax >= 0),
    total_price DECIMAL(12,2) GENERATED ALWAYS
        AS ((unit_price * quantity) - discount + tax) STORED,
    allocated_inventory_id VARCHAR(30),

    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    CHECK (discount <= unit_price * quantity)
);

CREATE INDEX idx_order_product ON order_items(order_id, product_id);
CREATE INDEX idx_product_sales ON order_items(product_id, variant_id);

COMMENT ON TABLE order_items IS 'Line items within customer orders';

CREATE TABLE returns (
    return_id VARCHAR(40) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    quantity INTEGER CHECK (quantity > 0),
    reason VARCHAR(100),
    return_status VARCHAR(30) DEFAULT 'requested'
        CHECK (return_status IN ('requested', 'approved', 'received', 'inspected', 'refunded', 'rejected')),
    returned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    refund_amount DECIMAL(10,2) CHECK (refund_amount >= 0),
    restocking_fee DECIMAL(10,2) DEFAULT 0.00 CHECK (restocking_fee >= 0),
    inspection_notes TEXT,

    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id)
);

CREATE INDEX idx_return_status ON returns(return_status, returned_at);
CREATE INDEX idx_product_returns ON returns(product_id, variant_id, returned_at);

COMMENT ON TABLE returns IS 'Product return requests and processing';

-- DOMAIN 5: ANALYTICS (5 tables)
-- ============================================

CREATE TABLE website_sessions (
    session_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(20),
    entry_page VARCHAR(200),
    exit_page VARCHAR(200),
    session_duration_seconds INTEGER CHECK (session_duration_seconds >= 0),
    device_type VARCHAR(30),
    browser VARCHAR(50),
    country VARCHAR(50),
    region VARCHAR(50),
    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    bounce_rate BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE INDEX idx_session_analytics ON website_sessions(session_start, country, device_type);
CREATE INDEX idx_customer_sessions ON website_sessions(customer_id, session_start DESC);

COMMENT ON TABLE website_sessions IS 'Website user session tracking';

CREATE TABLE campaigns (
    campaign_id VARCHAR(30) PRIMARY KEY,
    campaign_name VARCHAR(100) NOT NULL,
    channel VARCHAR(30) NOT NULL
        CHECK (channel IN ('email', 'social', 'search', 'affiliate', 'display')),
    budget DECIMAL(12,2) CHECK (budget >= 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    target_countries JSONB,
    target_segments JSONB,
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'completed', 'cancelled')),
    campaign_manager VARCHAR(50),

    CHECK (end_date >= start_date)
);

CREATE INDEX idx_campaign_dates ON campaigns(start_date, end_date, status);
CREATE INDEX idx_campaign_channel ON campaigns(channel, status);

COMMENT ON TABLE campaigns IS 'Marketing campaigns with targeting';

CREATE TABLE conversion_funnels (
    funnel_id VARCHAR(40) PRIMARY KEY,
    campaign_id VARCHAR(30) NOT NULL,
    stage_name VARCHAR(50) NOT NULL,
    stage_order INTEGER NOT NULL CHECK (stage_order >= 1),
    visitors_count INTEGER DEFAULT 0 CHECK (visitors_count >= 0),
    conversions_count INTEGER DEFAULT 0 CHECK (conversions_count >= 0),
    conversion_rate DECIMAL(5,2) GENERATED ALWAYS
        AS (CASE WHEN visitors_count > 0 THEN conversions_count * 100.0 / visitors_count ELSE 0 END) STORED,
    avg_time_to_convert_hours DECIMAL(6,2) CHECK (avg_time_to_convert_hours >= 0),
    notes TEXT,

    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id),
    UNIQUE (campaign_id, stage_name)
);

CREATE INDEX idx_funnel_performance ON conversion_funnels(campaign_id, stage_order, conversion_rate);

COMMENT ON TABLE conversion_funnels IS 'Conversion funnel tracking for campaigns';

CREATE TABLE customer_lifetime_value (
    clv_id VARCHAR(40) PRIMARY KEY,
    customer_id VARCHAR(20) NOT NULL,
    calculated_clv DECIMAL(12,2) CHECK (calculated_clv >= 0),
    calculation_date DATE NOT NULL,
    time_horizon VARCHAR(20) NOT NULL
        CHECK (time_horizon IN ('1_year', '2_year', '3_year', 'lifetime')),
    purchase_frequency DECIMAL(5,2) CHECK (purchase_frequency >= 0),
    avg_order_value DECIMAL(10,2) CHECK (avg_order_value >= 0),
    predicted_churn_probability DECIMAL(4,3) CHECK (predicted_churn_probability BETWEEN 0 AND 1),
    segment VARCHAR(30),

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    UNIQUE (customer_id, calculation_date, time_horizon)
);

CREATE INDEX idx_clv_segment ON customer_lifetime_value(segment, calculated_clv DESC);
CREATE INDEX idx_churn_risk ON customer_lifetime_value(predicted_churn_probability DESC, customer_id);

COMMENT ON TABLE customer_lifetime_value IS 'Customer lifetime value calculations';

CREATE TABLE demand_forecasts (
    forecast_id VARCHAR(50) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    forecast_date DATE NOT NULL,
    forecasted_quantity INTEGER CHECK (forecasted_quantity >= 0),
    confidence_interval_lower INTEGER CHECK (confidence_interval_lower >= 0),
    confidence_interval_upper INTEGER CHECK (confidence_interval_upper >= confidence_interval_lower),
    method VARCHAR(50)
        CHECK (method IN ('arima', 'prophet', 'ensemble', 'exponential_smoothing')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accuracy_score DECIMAL(5,4) CHECK (accuracy_score BETWEEN 0 AND 1),

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    UNIQUE (product_id, variant_id, forecast_date, method)
);

CREATE INDEX idx_forecast_horizon ON demand_forecasts(forecast_date, product_id);
CREATE INDEX idx_forecast_accuracy ON demand_forecasts(accuracy_score DESC, method);

COMMENT ON TABLE demand_forecasts IS 'Product demand forecasts for inventory planning';

-- DOMAIN 6: FINANCE (4 tables)
-- ============================================

CREATE TABLE transactions (
    transaction_id VARCHAR(50) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    transaction_type VARCHAR(30) NOT NULL
        CHECK (transaction_type IN ('sale', 'refund', 'payment', 'fee', 'adjustment')),
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    fx_rate DECIMAL(8,4) DEFAULT 1.0000 CHECK (fx_rate > 0),
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'failed', 'reversed')),
    payment_gateway VARCHAR(50),
    settlement_date DATE,

    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE INDEX idx_transaction_dates ON transactions(transaction_date, status);
CREATE INDEX idx_order_transactions ON transactions(order_id, transaction_type);
CREATE INDEX idx_settlement ON transactions(settlement_date, payment_gateway);

COMMENT ON TABLE transactions IS 'Financial transactions for orders';

CREATE TABLE invoices (
    invoice_id VARCHAR(40) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    total_amount DECIMAL(12,2) CHECK (total_amount >= 0),
    paid_amount DECIMAL(12,2) DEFAULT 0.00 CHECK (paid_amount >= 0),
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'overdue')),
    payment_terms VARCHAR(30),
    late_fee_applied DECIMAL(10,2) DEFAULT 0.00 CHECK (late_fee_applied >= 0),
    last_reminder_sent DATE,

    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    CHECK (due_date >= invoice_date),
    CHECK (paid_amount <= total_amount)
);

CREATE INDEX idx_invoice_status_dates ON invoices(status, due_date, invoice_date);
CREATE INDEX idx_overdue_invoices ON invoices(due_date) WHERE status = 'overdue';

COMMENT ON TABLE invoices IS 'Customer invoices with payment tracking';

CREATE TABLE cost_allocations (
    allocation_id VARCHAR(50) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    campaign_id VARCHAR(30) NOT NULL,
    cost_center VARCHAR(50) NOT NULL,
    amount DECIMAL(12,2) CHECK (amount >= 0),
    allocation_method VARCHAR(40) NOT NULL
        CHECK (allocation_method IN ('direct', 'proportional', 'activity_based')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    allocated_by VARCHAR(20) NOT NULL,

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id),
    CHECK (period_end > period_start)
);

CREATE INDEX idx_allocation_period ON cost_allocations(period_start, period_end, cost_center);
CREATE INDEX idx_product_campaign_costs ON cost_allocations(product_id, campaign_id);

COMMENT ON TABLE cost_allocations IS 'Cost allocation across products and campaigns';

CREATE TABLE profitability_analysis (
    analysis_id VARCHAR(50) PRIMARY KEY,
    product_id VARCHAR(20) NOT NULL,
    variant_id VARCHAR(25) NOT NULL,
    period VARCHAR(7) NOT NULL,  -- YYYY-MM format
    revenue DECIMAL(15,2) CHECK (revenue >= 0),
    cost_of_goods_sold DECIMAL(15,2) CHECK (cost_of_goods_sold >= 0),
    operating_expenses DECIMAL(15,2) CHECK (operating_expenses >= 0),
    shipping_costs DECIMAL(12,2) CHECK (shipping_costs >= 0),
    marketing_costs DECIMAL(12,2) CHECK (marketing_costs >= 0),
    net_profit DECIMAL(15,2) GENERATED ALWAYS
        AS (revenue - cost_of_goods_sold - operating_expenses - shipping_costs - marketing_costs) STORED,
    margin_percentage DECIMAL(6,2) GENERATED ALWAYS
        AS (CASE WHEN revenue > 0 THEN (revenue - cost_of_goods_sold) * 100.0 / revenue ELSE 0 END) STORED,
    currency VARCHAR(3) DEFAULT 'USD',

    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (variant_id) REFERENCES product_variants(variant_id),
    UNIQUE (product_id, variant_id, period)
);

CREATE INDEX idx_profitability_period ON profitability_analysis(period, net_profit DESC);
CREATE INDEX idx_margin_analysis ON profitability_analysis(margin_percentage DESC, product_id);

COMMENT ON TABLE profitability_analysis IS 'Monthly profitability analysis by product';

-- DOMAIN 7: HR (2 tables)
-- ============================================

CREATE TABLE employees (
    employee_id VARCHAR(20) PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    department VARCHAR(50) NOT NULL,
    job_title VARCHAR(100) NOT NULL,
    hire_date DATE NOT NULL,
    manager_id VARCHAR(20),
    country VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    cost_center VARCHAR(20),
    employment_type VARCHAR(20) NOT NULL
        CHECK (employment_type IN ('full_time', 'part_time', 'contractor')),

    FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);

CREATE INDEX idx_employee_department ON employees(department, job_title);
CREATE INDEX idx_manager_hierarchy ON employees(manager_id, employee_id);
CREATE INDEX idx_location_employees ON employees(country, region, department);

COMMENT ON TABLE employees IS 'Employee master data with reporting hierarchy';

CREATE TABLE departments (
    department_id VARCHAR(20) PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL,
    cost_center_code VARCHAR(20) UNIQUE NOT NULL,
    head_count_budget INTEGER CHECK (head_count_budget >= 0),
    actual_head_count INTEGER DEFAULT 0 CHECK (actual_head_count >= 0),
    department_manager_id VARCHAR(20) NOT NULL,
    parent_department_id VARCHAR(20),
    location VARCHAR(50) NOT NULL,

    FOREIGN KEY (department_manager_id) REFERENCES employees(employee_id),
    FOREIGN KEY (parent_department_id) REFERENCES departments(department_id)
);

CREATE INDEX idx_department_hierarchy ON departments(parent_department_id, department_id);
CREATE INDEX idx_cost_center ON departments(cost_center_code);

COMMENT ON TABLE departments IS 'Department organization structure';

-- ============================================
-- FOREIGN KEY ADDITIONS (Deferred due to dependencies)
-- ============================================

-- Add warehouse_id FK to finished_goods_inventory (depends on warehouses)
ALTER TABLE finished_goods_inventory
ADD FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id);

-- Add warehouse_id FK to raw_material_inventory (depends on warehouses)
ALTER TABLE raw_material_inventory
ADD FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id);

-- Add warehouse_id FK to safety_stock_levels (depends on warehouses)
ALTER TABLE safety_stock_levels
ADD FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id);

-- Add warehouse_id FK to stock_reconciliation (depends on warehouses)
ALTER TABLE stock_reconciliation
ADD FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id);

-- Add warehouse_id FK to obsolete_inventory (depends on warehouses)
ALTER TABLE obsolete_inventory
ADD FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id);

-- Add to_customer_id FK to shipments (depends on customers)
ALTER TABLE shipments
ADD FOREIGN KEY (to_customer_id) REFERENCES customers(customer_id);

-- Add performed_by FK to inventory_transactions (depends on employees)
ALTER TABLE inventory_transactions
ADD FOREIGN KEY (performed_by) REFERENCES employees(employee_id);

-- Add reconciled_by FK to stock_reconciliation (depends on employees)
ALTER TABLE stock_reconciliation
ADD FOREIGN KEY (reconciled_by) REFERENCES employees(employee_id);

-- Add recorded_by FK to obsolete_inventory (depends on employees)
ALTER TABLE obsolete_inventory
ADD FOREIGN KEY (recorded_by) REFERENCES employees(employee_id);

-- Add verified_by FK to customs_documentation (depends on employees)
ALTER TABLE customs_documentation
ADD FOREIGN KEY (verified_by) REFERENCES employees(employee_id);

-- Add inspector_id FK to quality_inspections (depends on employees)
ALTER TABLE quality_inspections
ADD FOREIGN KEY (inspector_id) REFERENCES employees(employee_id);

-- Add allocated_inventory_id FK to order_items (depends on finished_goods_inventory)
ALTER TABLE order_items
ADD FOREIGN KEY (allocated_inventory_id) REFERENCES finished_goods_inventory(inventory_id);

-- Add allocated_by FK to cost_allocations (depends on employees)
ALTER TABLE cost_allocations
ADD FOREIGN KEY (allocated_by) REFERENCES employees(employee_id);

-- Add manager_id FK to warehouses (depends on employees)
ALTER TABLE warehouses
ADD FOREIGN KEY (manager_id) REFERENCES employees(employee_id);

-- ============================================
-- COMPOSITE INDEXES FOR PERFORMANCE
-- ============================================

-- Cross-domain query performance
CREATE INDEX idx_product_warehouse_availability
ON finished_goods_inventory(warehouse_id, product_id, variant_id, available_quantity);

CREATE INDEX idx_order_fulfillment
ON orders(status, fulfillment_priority, order_date);

CREATE INDEX idx_inventory_transaction_audit
ON inventory_transactions(transaction_time DESC, inventory_type, inventory_id);

CREATE INDEX idx_production_quality
ON production_runs(yield_percentage, production_line_id, start_time);

CREATE INDEX idx_customer_order_history
ON orders(customer_id, order_date DESC, total_amount);

-- ============================================
-- VIEWS FOR COMMON REPORTING
-- ============================================

CREATE VIEW vw_available_inventory AS
SELECT
    fgi.inventory_id,
    fgi.product_id,
    p.product_name,
    fgi.variant_id,
    pv.sku,
    fgi.warehouse_id,
    w.warehouse_name,
    w.country,
    w.region,
    fgi.quantity,
    fgi.allocated_quantity,
    fgi.available_quantity,
    ssl.safety_stock_quantity,
    CASE
        WHEN fgi.available_quantity <= ssl.safety_stock_quantity THEN 'LOW'
        WHEN fgi.available_quantity <= ssl.reorder_point THEN 'REORDER'
        ELSE 'OK'
    END as stock_status,
    fgi.last_updated
FROM finished_goods_inventory fgi
JOIN products p ON fgi.product_id = p.product_id
JOIN product_variants pv ON fgi.variant_id = pv.variant_id
JOIN warehouses w ON fgi.warehouse_id = w.warehouse_id
LEFT JOIN safety_stock_levels ssl ON fgi.product_id = ssl.product_id
    AND fgi.variant_id = ssl.variant_id
    AND fgi.warehouse_id = ssl.warehouse_id
WHERE p.is_active = TRUE;

CREATE VIEW vw_order_fulfillment_status AS
SELECT
    o.order_id,
    o.customer_id,
    c.first_name,
    c.last_name,
    o.order_date,
    o.total_amount,
    o.status as order_status,
    o.fulfillment_priority,
    s.shipment_id,
    s.status as shipment_status,
    s.shipped_at,
    s.estimated_delivery,
    s.actual_delivery,
    COUNT(DISTINCT oi.order_item_id) as item_count,
    SUM(oi.quantity) as total_quantity,
    STRING_AGG(DISTINCT p.product_name, ',') as products
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p ON oi.product_id = p.product_id
LEFT JOIN shipments s ON o.order_id = s.order_id
GROUP BY o.order_id, o.customer_id, c.first_name, c.last_name, o.order_date,
         o.total_amount, o.status, o.fulfillment_priority,
         s.shipment_id, s.status, s.shipped_at, s.estimated_delivery, s.actual_delivery;

-- ============================================
-- END OF SCHEMA SETUP
-- ============================================
