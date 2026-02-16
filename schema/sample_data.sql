-- ============================================
-- COMPLETE SAMPLE DATA FOR EMULATED ENTERPRISE SCHEMA
-- All 35 tables with realistic, interconnected data
-- FK dependencies respected in insert order
-- Generated columns excluded from INSERTs
-- ============================================

-- ============================================
-- DOMAIN 1: MANUFACTURING
-- ============================================

-- 1. products (6 products)
INSERT INTO products (product_id, product_name, category, manufacturing_cost, weight_kg, geo_segments, is_active) VALUES
('P-1001', 'Quantum Laptop Pro', 'Electronics', 899.99, 1.85, '{"allowed_regions": ["NA", "EU", "SEA"], "restricted": ["CN"]}', TRUE),
('P-1002', 'Solar Powered Tablet', 'Electronics', 349.50, 0.68, '{"allowed_regions": ["SEA", "AU", "IN"], "restricted": ["RU"]}', TRUE),
('P-1003', 'Wireless Noise-Canceling Headphones', 'Audio', 129.99, 0.32, '{"allowed_regions": ["global"]}', TRUE),
('P-1004', 'Smart Fitness Watch', 'Wearables', 89.75, 0.045, '{"allowed_regions": ["NA", "EU", "JP"], "restricted": ["KR"]}', TRUE),
('P-1005', 'Portable Power Bank 20K', 'Accessories', 34.99, 0.48, '{"allowed_regions": ["global"]}', TRUE),
('P-1006', '4K Drone Pro', 'Electronics', 599.00, 1.20, '{"allowed_regions": ["NA", "EU"], "restricted": ["SEA", "ME"]}', TRUE);

-- 2. product_variants (2-3 variants per product)
INSERT INTO product_variants (variant_id, product_id, sku, size, color, regional_specs, price_adjustment) VALUES
-- Quantum Laptop variants
('PV-1001-01', 'P-1001', 'QLP-16GB-512GB', '16"', 'Space Gray', '{"voltage": "110-240V", "keyboard": "US-QWERTY"}', 0.00),
('PV-1001-02', 'P-1001', 'QLP-32GB-1TB', '16"', 'Silver', '{"voltage": "110-240V", "keyboard": "UK-QWERTY"}', 300.00),
('PV-1001-03', 'P-1001', 'QLP-16GB-512GB-SEA', '16"', 'Space Gray', '{"voltage": "220-240V", "keyboard": "SEA-QWERTY", "warranty": "2 years"}', 50.00),
-- Solar Tablet variants
('PV-1002-01', 'P-1002', 'SPT-10-64GB', '10"', 'Black', '{"solar_efficiency": "22%", "water_resistant": "IP67"}', 0.00),
('PV-1002-02', 'P-1002', 'SPT-10-128GB', '10"', 'White', '{"solar_efficiency": "22%", "water_resistant": "IP67"}', 80.00),
('PV-1002-03', 'P-1002', 'SPT-8-64GB', '8"', 'Blue', '{"solar_efficiency": "18%", "water_resistant": "IP54"}', -30.00),
-- Headphones variants
('PV-1003-01', 'P-1003', 'WH-1000XM5-BK', NULL, 'Black', '{"battery_life": "30 hours", "bluetooth": "5.2"}', 0.00),
('PV-1003-02', 'P-1003', 'WH-1000XM5-SV', NULL, 'Silver', '{"battery_life": "30 hours", "bluetooth": "5.2"}', 0.00),
('PV-1003-03', 'P-1003', 'WH-1000XM5-LTD', NULL, 'Midnight Blue', '{"battery_life": "30 hours", "bluetooth": "5.2", "limited_edition": true}', 50.00),
-- Smart Watch variants
('PV-1004-01', 'P-1004', 'SFW-45-BL', '45mm', 'Black', '{"heart_rate_monitor": true, "gps": true, "water_resistant": "5ATM"}', 0.00),
('PV-1004-02', 'P-1004', 'SFW-41-WH', '41mm', 'White', '{"heart_rate_monitor": true, "gps": true, "water_resistant": "5ATM"}', 0.00),
('PV-1004-03', 'P-1004', 'SFW-45-TI', '45mm', 'Titanium', '{"heart_rate_monitor": true, "gps": true, "water_resistant": "10ATM", "sapphire_glass": true}', 200.00),
-- Power Bank variants
('PV-1005-01', 'P-1005', 'PPB-20K-BK', NULL, 'Black', '{"capacity": "20000mAh", "fast_charging": "PD 3.0"}', 0.00),
('PV-1005-02', 'P-1005', 'PPB-20K-WH', NULL, 'White', '{"capacity": "20000mAh", "fast_charging": "PD 3.0"}', 0.00),
-- Drone variants
('PV-1006-01', 'P-1006', 'DRN-4K-PRO', NULL, 'Gray', '{"camera": "4K 60fps", "flight_time": "32 mins", "range": "10km"}', 0.00),
('PV-1006-02', 'P-1006', 'DRN-4K-PRO-FLY', NULL, 'Gray', '{"camera": "4K 60fps", "flight_time": "32 mins", "range": "10km", "fly_more_combo": true}', 150.00);

-- 3. suppliers (5 suppliers)
INSERT INTO suppliers (supplier_id, supplier_name, country, reliability_score, avg_lead_time_days, payment_terms) VALUES
('SUP-001', 'Precision Components Ltd', 'Taiwan', 0.92, 21, 'Net 30'),
('SUP-002', 'Global Materials Inc', 'China', 0.85, 45, 'Net 60'),
('SUP-003', 'Quality Electronics Corp', 'South Korea', 0.95, 14, 'Net 15'),
('SUP-004', 'Battery Solutions Co', 'Japan', 0.88, 28, 'Net 45'),
('SUP-005', 'Solar Tech GmbH', 'Germany', 0.91, 35, 'Net 30');

-- 4. raw_materials (10 materials)
INSERT INTO raw_materials (material_id, material_name, supplier_id, unit_cost, unit_of_measure, lead_time_days, min_order_quantity) VALUES
('RM-001', 'Aluminum Alloy 6061', 'SUP-001', 3.45, 'kg', 21, 1000),
('RM-002', 'OLED Display 15.6"', 'SUP-002', 89.99, 'piece', 45, 500),
('RM-003', 'Lithium-ion Battery 100Wh', 'SUP-004', 42.50, 'piece', 28, 1000),
('RM-004', 'Solar Panel 10W', 'SUP-005', 18.75, 'piece', 35, 2000),
('RM-005', 'Qualcomm Snapdragon 8 Gen 2', 'SUP-003', 112.00, 'piece', 14, 1000),
('RM-006', 'Memory 16GB LPDDR5', 'SUP-003', 38.20, 'piece', 14, 2000),
('RM-007', 'NVMe SSD 512GB', 'SUP-002', 45.80, 'piece', 45, 1000),
('RM-008', 'Bluetooth 5.3 Module', 'SUP-001', 8.90, 'piece', 21, 5000),
('RM-009', 'Camera Sensor 48MP', 'SUP-003', 32.15, 'piece', 14, 3000),
('RM-010', 'GPS Module', 'SUP-001', 6.75, 'piece', 21, 5000);

-- 5. bill_of_materials
INSERT INTO bill_of_materials (bom_id, product_id, material_id, quantity_required, scrap_factor, level) VALUES
-- Quantum Laptop BOM
('BOM-P1001-01', 'P-1001', 'RM-001', 0.85, 0.02, 1),
('BOM-P1001-02', 'P-1001', 'RM-002', 1.00, 0.01, 1),
('BOM-P1001-03', 'P-1001', 'RM-003', 1.00, 0.005, 1),
('BOM-P1001-04', 'P-1001', 'RM-005', 1.00, 0.001, 1),
('BOM-P1001-05', 'P-1001', 'RM-006', 1.00, 0.001, 1),
('BOM-P1001-06', 'P-1001', 'RM-007', 1.00, 0.001, 1),
-- Solar Tablet BOM
('BOM-P1002-01', 'P-1002', 'RM-001', 0.35, 0.03, 1),
('BOM-P1002-02', 'P-1002', 'RM-004', 1.00, 0.02, 1),
('BOM-P1002-03', 'P-1002', 'RM-003', 0.50, 0.005, 1),
('BOM-P1002-04', 'P-1002', 'RM-008', 1.00, 0.001, 1),
('BOM-P1002-05', 'P-1002', 'RM-009', 2.00, 0.001, 1),
-- Headphones BOM
('BOM-P1003-01', 'P-1003', 'RM-001', 0.15, 0.05, 1),
('BOM-P1003-02', 'P-1003', 'RM-003', 0.10, 0.01, 1),
('BOM-P1003-03', 'P-1003', 'RM-008', 1.00, 0.001, 1),
-- Smart Watch BOM
('BOM-P1004-01', 'P-1004', 'RM-001', 0.02, 0.10, 1),
('BOM-P1004-02', 'P-1004', 'RM-003', 0.05, 0.02, 1),
('BOM-P1004-03', 'P-1004', 'RM-010', 1.00, 0.001, 1),
('BOM-P1004-04', 'P-1004', 'RM-009', 1.00, 0.001, 1);

-- 6. production_lines
INSERT INTO production_lines (line_id, line_name, location, capacity_per_hour, maintenance_schedule, status, primary_product_category) VALUES
('PL-SG-01', 'Singapore Assembly Line 1', 'Singapore', 50, '{"downtime_hours_per_week": 4, "schedule": "sunday_0200-0600"}', 'active', 'Electronics'),
('PL-TW-01', 'Taiwan Component Line', 'Taiwan', 100, '{"downtime_hours_per_week": 8, "schedule": "saturday_full"}', 'active', 'Components'),
('PL-KR-01', 'Korea Quality Line', 'South Korea', 30, '{"downtime_hours_per_week": 2, "schedule": "wednesday_night"}', 'active', 'Audio');

-- 7. production_runs (GENERATED: yield_percentage)
INSERT INTO production_runs (run_id, product_id, variant_id, quantity, start_time, end_time, status, production_line_id, defects_count) VALUES
('RUN-2024-001', 'P-1001', 'PV-1001-01', 200, '2024-01-15 08:00:00', '2024-01-15 16:00:00', 'completed', 'PL-SG-01', 2),
('RUN-2024-002', 'P-1001', 'PV-1001-03', 100, '2024-01-16 09:00:00', '2024-01-16 14:00:00', 'completed', 'PL-SG-01', 1),
('RUN-2024-003', 'P-1003', 'PV-1003-01', 600, '2024-01-17 07:00:00', '2024-01-17 19:00:00', 'completed', 'PL-KR-01', 5),
('RUN-2024-004', 'P-1004', 'PV-1004-01', 400, '2024-01-18 10:00:00', '2024-01-18 18:00:00', 'in_progress', 'PL-TW-01', 0),
('RUN-2024-005', 'P-1006', 'PV-1006-01', 50, '2024-01-19 08:00:00', NULL, 'scheduled', 'PL-SG-01', 0),
('RUN-2024-006', 'P-1002', 'PV-1002-01', 300, '2024-02-10 06:00:00', '2024-02-10 18:00:00', 'completed', 'PL-SG-01', 3),
('RUN-2024-007', 'P-1005', 'PV-1005-01', 1000, '2024-03-01 07:00:00', '2024-03-02 07:00:00', 'completed', 'PL-TW-01', 8),
('RUN-2024-008', 'P-1003', 'PV-1003-02', 250, '2024-04-15 08:00:00', '2024-04-15 16:00:00', 'completed', 'PL-KR-01', 1);

-- ============================================
-- DOMAIN 7: HR (before quality_inspections for FK deps)
-- ============================================

-- 8. employees
INSERT INTO employees (employee_id, first_name, last_name, department, job_title, hire_date, manager_id, country, region, email, cost_center, employment_type) VALUES
('EMP-001', 'Robert', 'Chen', 'Executive', 'CEO', '2020-01-15', NULL, 'Singapore', 'SEA', 'robert.chen@company.com', 'CC-001', 'full_time'),
('EMP-002', 'Sarah', 'Johnson', 'Manufacturing', 'VP of Operations', '2021-03-10', 'EMP-001', 'USA', 'NA', 'sarah.johnson@company.com', 'CC-002', 'full_time'),
('EMP-003', 'David', 'Kim', 'Manufacturing', 'Production Manager', '2021-06-15', 'EMP-002', 'South Korea', 'KR', 'david.kim@company.com', 'CC-002', 'full_time'),
('EMP-004', 'Maria', 'Garcia', 'Quality', 'Quality Director', '2021-04-20', 'EMP-002', 'Spain', 'EU', 'maria.garcia@company.com', 'CC-003', 'full_time'),
('EMP-005', 'James', 'Wilson', 'Quality', 'Quality Inspector', '2022-01-10', 'EMP-004', 'UK', 'EU', 'james.wilson@company.com', 'CC-003', 'full_time'),
('EMP-006', 'Lisa', 'Wang', 'Logistics', 'Warehouse Manager', '2021-05-15', 'EMP-002', 'Singapore', 'SEA', 'lisa.wang@company.com', 'CC-004', 'full_time'),
('EMP-007', 'Thomas', 'Muller', 'Logistics', 'Shipping Coordinator', '2022-03-01', 'EMP-006', 'Germany', 'EU', 'thomas.muller@company.com', 'CC-004', 'full_time'),
('EMP-008', 'Akira', 'Tanaka', 'Sales', 'Sales Director', '2021-02-01', 'EMP-001', 'Japan', 'JP', 'akira.tanaka@company.com', 'CC-005', 'full_time'),
('EMP-009', 'Priya', 'Sharma', 'Finance', 'CFO', '2020-06-01', 'EMP-001', 'India', 'IN', 'priya.sharma@company.com', 'CC-006', 'full_time'),
('EMP-010', 'Michael', 'Brown', 'IT', 'CTO', '2020-03-15', 'EMP-001', 'USA', 'NA', 'michael.brown@company.com', 'CC-007', 'full_time');

-- Self-referencing CEO manager
UPDATE employees SET manager_id = 'EMP-001' WHERE employee_id = 'EMP-001';

-- 9. departments
INSERT INTO departments (department_id, department_name, cost_center_code, head_count_budget, actual_head_count, department_manager_id, parent_department_id, location) VALUES
('DEPT-001', 'Executive Office', 'CC-001', 5, 1, 'EMP-001', NULL, 'Singapore'),
('DEPT-002', 'Operations', 'CC-002', 50, 2, 'EMP-002', 'DEPT-001', 'Global'),
('DEPT-003', 'Quality Assurance', 'CC-003', 20, 2, 'EMP-004', 'DEPT-002', 'Global'),
('DEPT-004', 'Logistics', 'CC-004', 30, 2, 'EMP-006', 'DEPT-002', 'Singapore'),
('DEPT-005', 'Sales & Marketing', 'CC-005', 25, 1, 'EMP-008', 'DEPT-001', 'Tokyo'),
('DEPT-006', 'Finance', 'CC-006', 15, 1, 'EMP-009', 'DEPT-001', 'Bangalore'),
('DEPT-007', 'IT & Engineering', 'CC-007', 40, 1, 'EMP-010', 'DEPT-001', 'San Francisco');

-- 10. quality_inspections
INSERT INTO quality_inspections (inspection_id, run_id, inspector_id, passed, defects, inspection_time, notes) VALUES
('QI-2024-001', 'RUN-2024-001', 'EMP-005', TRUE, NULL, '2024-01-15 17:00:00', 'All units passed visual and functional tests'),
('QI-2024-002', 'RUN-2024-002', 'EMP-005', TRUE, '{"type": "cosmetic", "count": 1, "severity": "low"}', '2024-01-16 15:00:00', 'One unit with minor scratch, repackaged as B-grade'),
('QI-2024-003', 'RUN-2024-003', 'EMP-005', FALSE, '{"type": "functional", "count": 5, "severity": "medium", "issue": "bluetooth pairing failure"}', '2024-01-17 20:00:00', '5 units failed BT test, sent for rework'),
('QI-2024-004', 'RUN-2024-006', 'EMP-005', TRUE, '{"type": "cosmetic", "count": 2, "severity": "low"}', '2024-02-10 19:30:00', 'Minor screen blemishes on 2 units, within tolerance'),
('QI-2024-005', 'RUN-2024-007', 'EMP-004', TRUE, '{"type": "functional", "count": 3, "severity": "low"}', '2024-03-02 10:00:00', '3 units with slightly lower charge capacity, marked B-grade'),
('QI-2024-006', 'RUN-2024-008', 'EMP-005', TRUE, NULL, '2024-04-15 17:00:00', 'All units passed all tests');

-- ============================================
-- DOMAIN 3: LOGISTICS
-- ============================================

-- 11. warehouses
INSERT INTO warehouses (warehouse_id, warehouse_name, location, type, capacity_sqft, country, region, manager_id, operational_hours) VALUES
('WH-SG-01', 'Singapore Central Hub', 'Singapore', 'central', 100000, 'Singapore', 'SEA', 'EMP-006', '{"weekdays": "24/7", "weekends": "06:00-22:00"}'),
('WH-US-01', 'Los Angeles Distribution', 'Los Angeles, CA', 'regional', 75000, 'USA', 'NA', 'EMP-006', '{"weekdays": "06:00-22:00", "weekends": "08:00-18:00"}'),
('WH-EU-01', 'Rotterdam EU Hub', 'Rotterdam', 'regional', 80000, 'Netherlands', 'EU', 'EMP-007', '{"weekdays": "06:00-22:00", "weekends": "closed"}'),
('WH-JP-01', 'Tokyo Local Warehouse', 'Tokyo', 'local', 25000, 'Japan', 'JP', 'EMP-008', '{"weekdays": "08:00-20:00", "weekends": "09:00-17:00"}'),
('WH-AU-01', 'Sydney Pop-up', 'Sydney', 'popup', 10000, 'Australia', 'AU', 'EMP-006', '{"weekdays": "09:00-17:00", "weekends": "closed"}');

-- 12. delivery_partners
INSERT INTO delivery_partners (partner_id, partner_name, service_type, coverage_countries, performance_score, contract_start_date, contract_end_date, rate_card) VALUES
('DP-001', 'FedEx International', 'express', '["US", "CA", "MX", "UK", "DE", "FR", "SG", "JP", "AU"]', 0.94, '2024-01-01', '2025-12-31', '{"per_kg": 12.50, "minimum": 25.00, "express_surcharge": 15.00}'),
('DP-002', 'Maersk Logistics', 'freight', '["global"]', 0.88, '2024-03-15', '2026-03-14', '{"per_kg": 2.80, "minimum": 500.00, "container_20ft": 3500.00}'),
('DP-003', 'DHL Express', 'express', '["US", "UK", "DE", "SG", "JP", "KR", "AU", "IN"]', 0.91, '2024-02-01', '2025-08-31', '{"per_kg": 11.00, "minimum": 20.00, "express_surcharge": 12.00}'),
('DP-004', 'GrabExpress SEA', 'last_mile', '["SG", "MY", "TH", "VN", "PH", "ID"]', 0.82, '2024-06-01', '2025-05-31', '{"per_delivery": 5.50, "per_km": 0.80}'),
('DP-005', 'Japan Post Logistics', 'standard', '["JP"]', 0.96, '2024-01-15', '2025-12-31', '{"per_kg": 4.20, "minimum": 10.00}');

-- 13. shipping_routes
INSERT INTO shipping_routes (route_id, from_warehouse_id, to_warehouse_id, distance_km, estimated_days, cost_per_kg, carrier_id, is_active, customs_required) VALUES
('RT-SG-US-01', 'WH-SG-01', 'WH-US-01', 15300, 14, 3.50, 'DP-002', TRUE, TRUE),
('RT-SG-EU-01', 'WH-SG-01', 'WH-EU-01', 10200, 18, 3.20, 'DP-002', TRUE, TRUE),
('RT-SG-JP-01', 'WH-SG-01', 'WH-JP-01', 5300, 5, 8.50, 'DP-001', TRUE, TRUE),
('RT-SG-AU-01', 'WH-SG-01', 'WH-AU-01', 6300, 7, 7.80, 'DP-003', TRUE, TRUE),
('RT-US-EU-01', 'WH-US-01', 'WH-EU-01', 8900, 10, 4.10, 'DP-001', TRUE, TRUE),
('RT-EU-JP-01', 'WH-EU-01', 'WH-JP-01', 9500, 12, 5.60, 'DP-003', TRUE, TRUE),
('RT-JP-SG-01', 'WH-JP-01', 'WH-SG-01', 5300, 4, 6.90, 'DP-005', TRUE, TRUE);

-- ============================================
-- DOMAIN 2: INVENTORY MANAGEMENT
-- ============================================

-- 14. finished_goods_inventory (GENERATED: available_quantity)
INSERT INTO finished_goods_inventory (inventory_id, product_id, variant_id, warehouse_id, quantity, allocated_quantity, batch_number) VALUES
('INV-SG-P1001-001', 'P-1001', 'PV-1001-01', 'WH-SG-01', 150, 25, 'BATCH-2024-Q1-001'),
('INV-SG-P1001-002', 'P-1001', 'PV-1001-03', 'WH-SG-01', 75, 10, 'BATCH-2024-Q1-002'),
('INV-US-P1001-001', 'P-1001', 'PV-1001-01', 'WH-US-01', 200, 50, 'BATCH-2024-Q1-003'),
('INV-US-P1003-001', 'P-1003', 'PV-1003-01', 'WH-US-01', 500, 125, 'BATCH-2024-Q1-004'),
('INV-EU-P1004-001', 'P-1004', 'PV-1004-01', 'WH-EU-01', 300, 75, 'BATCH-2024-Q1-005'),
('INV-JP-P1002-001', 'P-1002', 'PV-1002-01', 'WH-JP-01', 100, 20, 'BATCH-2024-Q1-006'),
('INV-SG-P1005-001', 'P-1005', 'PV-1005-01', 'WH-SG-01', 1000, 200, 'BATCH-2024-Q1-007'),
('INV-AU-P1003-001', 'P-1003', 'PV-1003-01', 'WH-AU-01', 50, 5, 'BATCH-2024-Q1-008'),
('INV-SG-P1006-001', 'P-1006', 'PV-1006-01', 'WH-SG-01', 5, 3, 'BATCH-2024-Q1-009'),
('INV-EU-P1003-001', 'P-1003', 'PV-1003-02', 'WH-EU-01', 220, 30, 'BATCH-2024-Q2-001'),
('INV-US-P1005-001', 'P-1005', 'PV-1005-02', 'WH-US-01', 800, 100, 'BATCH-2024-Q2-002'),
('INV-JP-P1004-001', 'P-1004', 'PV-1004-02', 'WH-JP-01', 180, 40, 'BATCH-2024-Q2-003');

-- 15. safety_stock_levels
INSERT INTO safety_stock_levels (product_id, variant_id, warehouse_id, safety_stock_quantity, reorder_point, calculation_method, service_level_target) VALUES
('P-1001', 'PV-1001-01', 'WH-SG-01', 20, 50, 'historical_demand', 0.95),
('P-1001', 'PV-1001-03', 'WH-SG-01', 10, 25, 'historical_demand', 0.90),
('P-1003', 'PV-1003-01', 'WH-US-01', 100, 250, 'forecast_based', 0.98),
('P-1004', 'PV-1004-01', 'WH-EU-01', 50, 120, 'historical_demand', 0.95),
('P-1006', 'PV-1006-01', 'WH-SG-01', 10, 25, 'forecast_based', 0.99),
('P-1005', 'PV-1005-01', 'WH-SG-01', 150, 400, 'historical_demand', 0.95),
('P-1002', 'PV-1002-01', 'WH-JP-01', 15, 40, 'forecast_based', 0.90),
('P-1003', 'PV-1003-02', 'WH-EU-01', 40, 100, 'historical_demand', 0.95);

-- 16. raw_material_inventory
INSERT INTO raw_material_inventory (inventory_id, material_id, warehouse_id, quantity, allocated_quantity, unit_of_measure, received_date, expiry_date, supplier_batch) VALUES
('RMI-001', 'RM-001', 'WH-SG-01', 5000.000, 850.000, 'kg', '2024-01-05', NULL, 'SUP001-B2024-001'),
('RMI-002', 'RM-002', 'WH-SG-01', 800.000, 200.000, 'piece', '2024-01-10', NULL, 'SUP002-B2024-001'),
('RMI-003', 'RM-003', 'WH-SG-01', 2500.000, 500.000, 'piece', '2024-01-08', '2026-01-08', 'SUP004-B2024-001'),
('RMI-004', 'RM-004', 'WH-SG-01', 3000.000, 300.000, 'piece', '2024-02-01', NULL, 'SUP005-B2024-001'),
('RMI-005', 'RM-005', 'WH-SG-01', 1200.000, 300.000, 'piece', '2024-01-12', NULL, 'SUP003-B2024-001'),
('RMI-006', 'RM-006', 'WH-SG-01', 3500.000, 700.000, 'piece', '2024-01-12', NULL, 'SUP003-B2024-002'),
('RMI-007', 'RM-007', 'WH-SG-01', 1500.000, 400.000, 'piece', '2024-01-15', NULL, 'SUP002-B2024-002'),
('RMI-008', 'RM-008', 'WH-SG-01', 8000.000, 600.000, 'piece', '2024-01-20', NULL, 'SUP001-B2024-002'),
('RMI-009', 'RM-009', 'WH-SG-01', 4000.000, 1000.000, 'piece', '2024-01-14', NULL, 'SUP003-B2024-003'),
('RMI-010', 'RM-010', 'WH-SG-01', 6000.000, 400.000, 'piece', '2024-01-22', NULL, 'SUP001-B2024-003');

-- 17. inventory_transactions
INSERT INTO inventory_transactions (transaction_id, transaction_type, inventory_type, inventory_id, quantity_change, reference_id, transaction_time, performed_by, notes) VALUES
('IT-2024-001', 'RECEIPT', 'FINISHED_GOODS', 'INV-SG-P1001-001', 200.000, 'RUN-2024-001', '2024-01-15 17:30:00', 'EMP-006', 'Production run RUN-2024-001 completed, 200 units received'),
('IT-2024-002', 'RECEIPT', 'FINISHED_GOODS', 'INV-SG-P1001-002', 100.000, 'RUN-2024-002', '2024-01-16 15:30:00', 'EMP-006', 'Production run RUN-2024-002 completed'),
('IT-2024-003', 'ALLOCATION', 'FINISHED_GOODS', 'INV-SG-P1001-001', -25.000, 'ORD-2024-001', '2024-01-20 10:00:00', 'EMP-006', 'Allocated for order ORD-2024-001'),
('IT-2024-004', 'ISSUE', 'RAW_MATERIAL', 'RMI-001', -170.000, 'RUN-2024-001', '2024-01-15 07:00:00', 'EMP-003', 'Issued aluminum for laptop production'),
('IT-2024-005', 'ISSUE', 'RAW_MATERIAL', 'RMI-002', -200.000, 'RUN-2024-001', '2024-01-15 07:00:00', 'EMP-003', 'Issued OLED displays'),
('IT-2024-006', 'TRANSFER', 'FINISHED_GOODS', 'INV-US-P1001-001', 50.000, 'TRANS-SG-US-001', '2024-02-05 09:00:00', 'EMP-007', 'Transfer from Singapore to LA warehouse'),
('IT-2024-007', 'RECEIPT', 'FINISHED_GOODS', 'INV-US-P1003-001', 600.000, 'RUN-2024-003', '2024-01-18 08:00:00', 'EMP-006', 'Headphones batch received'),
('IT-2024-008', 'ADJUSTMENT', 'FINISHED_GOODS', 'INV-AU-P1003-001', -2.000, 'ADJ-2024-001', '2024-03-15 14:00:00', 'EMP-006', 'Stock count adjustment - 2 units damaged in transit'),
('IT-2024-009', 'RECEIPT', 'RAW_MATERIAL', 'RMI-004', 3000.000, 'PO-2024-005', '2024-02-01 10:00:00', 'EMP-003', 'Solar panels received from Solar Tech GmbH'),
('IT-2024-010', 'ALLOCATION', 'FINISHED_GOODS', 'INV-EU-P1004-001', -75.000, 'ORD-2024-003', '2024-02-28 11:00:00', 'EMP-007', 'Allocated watches for EU order');

-- 18. inventory_valuation
INSERT INTO inventory_valuation (valuation_id, product_id, valuation_method, unit_value, total_value, as_of_date, currency, valuation_basis) VALUES
('VAL-P1001-2024Q1-FIFO', 'P-1001', 'FIFO', 899.9900, 382495.75, '2024-03-31', 'USD', 'cost'),
('VAL-P1001-2024Q1-WAC', 'P-1001', 'WAC', 912.5000, 388312.50, '2024-03-31', 'USD', 'lower_of_cost_or_market'),
('VAL-P1002-2024Q1-FIFO', 'P-1002', 'FIFO', 349.5000, 34950.00, '2024-03-31', 'USD', 'cost'),
('VAL-P1003-2024Q1-FIFO', 'P-1003', 'FIFO', 129.9900, 100292.30, '2024-03-31', 'USD', 'cost'),
('VAL-P1004-2024Q1-FIFO', 'P-1004', 'FIFO', 89.7500, 26925.00, '2024-03-31', 'USD', 'cost'),
('VAL-P1005-2024Q1-FIFO', 'P-1005', 'FIFO', 34.9900, 34990.00, '2024-03-31', 'USD', 'cost'),
('VAL-P1006-2024Q1-FIFO', 'P-1006', 'FIFO', 599.0000, 2995.00, '2024-03-31', 'USD', 'cost'),
('VAL-P1001-2024Q2-FIFO', 'P-1001', 'FIFO', 905.2500, 398310.00, '2024-06-30', 'USD', 'cost'),
('VAL-P1003-2024Q2-FIFO', 'P-1003', 'FIFO', 132.5000, 92750.00, '2024-06-30', 'USD', 'lower_of_cost_or_market'),
('VAL-P1004-2024Q2-FIFO', 'P-1004', 'FIFO', 91.0000, 43680.00, '2024-06-30', 'USD', 'cost');

-- 19. stock_reconciliation (GENERATED: discrepancy_amount)
INSERT INTO stock_reconciliation (reconciliation_id, warehouse_id, product_id, variant_id, expected_quantity, actual_quantity, discrepancy_reason, reconciled_by, reconciled_at) VALUES
('RECON-2024-Q1-001', 'WH-SG-01', 'P-1001', 'PV-1001-01', 150, 148, 'Two units found damaged during count', 'EMP-006', '2024-03-31 18:00:00'),
('RECON-2024-Q1-002', 'WH-US-01', 'P-1003', 'PV-1003-01', 500, 500, NULL, 'EMP-006', '2024-03-31 18:30:00'),
('RECON-2024-Q1-003', 'WH-EU-01', 'P-1004', 'PV-1004-01', 300, 299, 'One unit misplaced, found in wrong aisle', 'EMP-007', '2024-03-31 17:00:00'),
('RECON-2024-Q1-004', 'WH-JP-01', 'P-1002', 'PV-1002-01', 100, 100, NULL, 'EMP-008', '2024-03-31 16:00:00'),
('RECON-2024-Q1-005', 'WH-AU-01', 'P-1003', 'PV-1003-01', 50, 48, 'Two units damaged in transit, not recorded earlier', 'EMP-006', '2024-03-31 19:00:00'),
('RECON-2024-Q2-001', 'WH-SG-01', 'P-1005', 'PV-1005-01', 1000, 997, 'Three units with swollen batteries, removed', 'EMP-006', '2024-06-30 18:00:00');

-- 20. obsolete_inventory
INSERT INTO obsolete_inventory (product_id, variant_id, warehouse_id, quantity, write_off_value, reason, disposition, recorded_by, recorded_at) VALUES
('P-1001', 'PV-1001-01', 'WH-SG-01', 2, 1799.98, 'damaged', 'recycle', 'EMP-006', '2024-04-01 09:00:00'),
('P-1003', 'PV-1003-01', 'WH-AU-01', 2, 259.98, 'damaged', 'destroy', 'EMP-006', '2024-04-01 09:30:00'),
('P-1005', 'PV-1005-01', 'WH-SG-01', 3, 104.97, 'damaged', 'recycle', 'EMP-006', '2024-07-02 10:00:00'),
('P-1004', 'PV-1004-03', 'WH-EU-01', 5, 1448.75, 'discontinued', 'discount', 'EMP-007', '2024-09-15 11:00:00'),
('P-1002', 'PV-1002-03', 'WH-JP-01', 10, 3195.00, 'excess', 'donate', 'EMP-008', '2024-11-01 14:00:00');

-- ============================================
-- DOMAIN 4: E-COMMERCE
-- ============================================

-- 21. customers
INSERT INTO customers (customer_id, first_name, last_name, email, phone, country, customer_segment, acquisition_channel, lifetime_value, created_at) VALUES
('CUST-001', 'Emily', 'Thompson', 'emily.thompson@gmail.com', '+1-415-555-0101', 'USA', 'retail', 'search', 2450.00, '2024-01-10 14:30:00'),
('CUST-002', 'Raj', 'Patel', 'raj.patel@outlook.com', '+91-98765-43210', 'India', 'retail', 'social', 890.50, '2024-01-15 09:00:00'),
('CUST-003', 'Yuki', 'Nakamura', 'yuki.n@yahoo.co.jp', '+81-3-5555-0103', 'Japan', 'retail', 'affiliate', 1875.00, '2024-02-01 11:15:00'),
('CUST-004', 'Hans', 'Weber', 'h.weber@techcorp.de', '+49-30-555-0104', 'Germany', 'corporate', 'email', 15200.00, '2024-02-10 08:45:00'),
('CUST-005', 'Sophie', 'Laurent', 'sophie.l@company.fr', '+33-1-555-0105', 'France', 'wholesale', 'search', 28750.00, '2024-02-20 16:20:00'),
('CUST-006', 'Chen', 'Wei', 'chen.wei@techasia.sg', '+65-8555-0106', 'Singapore', 'corporate', 'email', 42100.00, '2024-03-05 10:00:00'),
('CUST-007', 'Olivia', 'Martinez', 'olivia.m@gmail.com', '+1-212-555-0107', 'USA', 'retail', 'display', 560.00, '2024-03-15 13:45:00'),
('CUST-008', 'Liam', 'OBrien', 'liam.ob@corporate.au', '+61-2-5555-0108', 'Australia', 'corporate', 'affiliate', 8900.00, '2024-04-01 07:30:00'),
('CUST-009', 'Aisha', 'Rahman', 'aisha.r@business.my', '+60-3-555-0109', 'Malaysia', 'wholesale', 'social', 19500.00, '2024-04-20 12:00:00'),
('CUST-010', 'Marco', 'Rossi', 'marco.r@email.it', '+39-06-555-0110', 'Italy', 'retail', 'search', 345.00, '2024-05-10 15:30:00');

-- 22. orders
INSERT INTO orders (order_id, customer_id, order_date, total_amount, status, currency, shipping_address, billing_address, payment_method, fulfillment_priority) VALUES
('ORD-2024-001', 'CUST-001', '2024-01-20 10:30:00', 1299.99, 'delivered', 'USD', '{"street": "123 Market St", "city": "San Francisco", "state": "CA", "zip": "94105", "country": "US"}', '{"street": "123 Market St", "city": "San Francisco", "state": "CA", "zip": "94105", "country": "US"}', 'credit_card', 'standard'),
('ORD-2024-002', 'CUST-002', '2024-02-05 14:00:00', 429.50, 'delivered', 'USD', '{"street": "45 MG Road", "city": "Bangalore", "state": "KA", "zip": "560001", "country": "IN"}', '{"street": "45 MG Road", "city": "Bangalore", "state": "KA", "zip": "560001", "country": "IN"}', 'debit_card', 'standard'),
('ORD-2024-003', 'CUST-004', '2024-02-28 09:15:00', 5390.00, 'delivered', 'EUR', '{"street": "Friedrichstr 100", "city": "Berlin", "zip": "10117", "country": "DE"}', '{"street": "Friedrichstr 100", "city": "Berlin", "zip": "10117", "country": "DE"}', 'bank_transfer', 'express'),
('ORD-2024-004', 'CUST-003', '2024-03-10 16:45:00', 349.50, 'delivered', 'JPY', '{"street": "2-1 Shibuya", "city": "Tokyo", "zip": "150-0002", "country": "JP"}', '{"street": "2-1 Shibuya", "city": "Tokyo", "zip": "150-0002", "country": "JP"}', 'credit_card', 'standard'),
('ORD-2024-005', 'CUST-005', '2024-03-25 11:00:00', 28750.00, 'shipped', 'EUR', '{"street": "15 Rue de Rivoli", "city": "Paris", "zip": "75001", "country": "FR"}', '{"street": "15 Rue de Rivoli", "city": "Paris", "zip": "75001", "country": "FR"}', 'bank_transfer', 'standard'),
('ORD-2024-006', 'CUST-006', '2024-04-12 08:30:00', 8499.00, 'delivered', 'SGD', '{"street": "1 Raffles Pl", "city": "Singapore", "zip": "048616", "country": "SG"}', '{"street": "1 Raffles Pl", "city": "Singapore", "zip": "048616", "country": "SG"}', 'credit_card', 'express'),
('ORD-2024-007', 'CUST-007', '2024-05-01 20:15:00', 179.98, 'delivered', 'USD', '{"street": "456 Broadway", "city": "New York", "state": "NY", "zip": "10013", "country": "US"}', '{"street": "456 Broadway", "city": "New York", "state": "NY", "zip": "10013", "country": "US"}', 'paypal', 'standard'),
('ORD-2024-008', 'CUST-008', '2024-05-20 03:00:00', 2699.00, 'processing', 'AUD', '{"street": "100 George St", "city": "Sydney", "state": "NSW", "zip": "2000", "country": "AU"}', '{"street": "100 George St", "city": "Sydney", "state": "NSW", "zip": "2000", "country": "AU"}', 'credit_card', 'standard'),
('ORD-2024-009', 'CUST-009', '2024-06-15 09:45:00', 19500.00, 'shipped', 'MYR', '{"street": "Jalan Sultan Ismail", "city": "Kuala Lumpur", "zip": "50250", "country": "MY"}', '{"street": "Jalan Sultan Ismail", "city": "Kuala Lumpur", "zip": "50250", "country": "MY"}', 'bank_transfer', 'scheduled'),
('ORD-2024-010', 'CUST-010', '2024-07-01 12:30:00', 129.99, 'cancelled', 'EUR', '{"street": "Via Roma 1", "city": "Rome", "zip": "00185", "country": "IT"}', '{"street": "Via Roma 1", "city": "Rome", "zip": "00185", "country": "IT"}', 'credit_card', 'standard'),
('ORD-2024-011', 'CUST-001', '2024-08-10 11:00:00', 1199.99, 'delivered', 'USD', '{"street": "123 Market St", "city": "San Francisco", "state": "CA", "zip": "94105", "country": "US"}', '{"street": "123 Market St", "city": "San Francisco", "state": "CA", "zip": "94105", "country": "US"}', 'credit_card', 'express'),
('ORD-2024-012', 'CUST-006', '2024-09-05 14:20:00', 33600.00, 'delivered', 'SGD', '{"street": "1 Raffles Pl", "city": "Singapore", "zip": "048616", "country": "SG"}', '{"street": "1 Raffles Pl", "city": "Singapore", "zip": "048616", "country": "SG"}', 'bank_transfer', 'standard');

-- 23. order_items (GENERATED: total_price)
INSERT INTO order_items (order_item_id, order_id, product_id, variant_id, quantity, unit_price, discount, tax, allocated_inventory_id) VALUES
('OI-2024-001-01', 'ORD-2024-001', 'P-1001', 'PV-1001-01', 1, 1299.99, 0.00, 0.00, 'INV-US-P1001-001'),
('OI-2024-002-01', 'ORD-2024-002', 'P-1002', 'PV-1002-01', 1, 349.50, 0.00, 80.00, 'INV-JP-P1002-001'),
('OI-2024-003-01', 'ORD-2024-003', 'P-1004', 'PV-1004-01', 20, 89.75, 100.00, 265.00, 'INV-EU-P1004-001'),
('OI-2024-003-02', 'ORD-2024-003', 'P-1003', 'PV-1003-01', 20, 129.99, 100.00, 330.00, 'INV-US-P1003-001'),
('OI-2024-004-01', 'ORD-2024-004', 'P-1002', 'PV-1002-01', 1, 349.50, 0.00, 0.00, 'INV-JP-P1002-001'),
('OI-2024-005-01', 'ORD-2024-005', 'P-1001', 'PV-1001-02', 15, 1599.99, 500.00, 1350.00, NULL),
('OI-2024-005-02', 'ORD-2024-005', 'P-1005', 'PV-1005-01', 100, 49.99, 200.00, 550.00, 'INV-SG-P1005-001'),
('OI-2024-006-01', 'ORD-2024-006', 'P-1001', 'PV-1001-01', 5, 1299.99, 250.00, 449.95, 'INV-SG-P1001-001'),
('OI-2024-006-02', 'ORD-2024-006', 'P-1006', 'PV-1006-01', 2, 899.00, 0.00, 143.84, 'INV-SG-P1006-001'),
('OI-2024-007-01', 'ORD-2024-007', 'P-1003', 'PV-1003-01', 1, 129.99, 0.00, 10.40, 'INV-US-P1003-001'),
('OI-2024-007-02', 'ORD-2024-007', 'P-1005', 'PV-1005-01', 1, 49.99, 0.00, 4.00, 'INV-SG-P1005-001'),
('OI-2024-008-01', 'ORD-2024-008', 'P-1006', 'PV-1006-02', 2, 1099.00, 0.00, 219.80, NULL),
('OI-2024-009-01', 'ORD-2024-009', 'P-1001', 'PV-1001-03', 10, 1349.99, 1000.00, 850.00, 'INV-SG-P1001-002'),
('OI-2024-009-02', 'ORD-2024-009', 'P-1003', 'PV-1003-01', 50, 129.99, 500.00, 410.00, 'INV-US-P1003-001'),
('OI-2024-010-01', 'ORD-2024-010', 'P-1003', 'PV-1003-02', 1, 129.99, 0.00, 0.00, NULL),
('OI-2024-011-01', 'ORD-2024-011', 'P-1001', 'PV-1001-01', 1, 1199.99, 0.00, 0.00, 'INV-US-P1001-001'),
('OI-2024-012-01', 'ORD-2024-012', 'P-1001', 'PV-1001-01', 20, 1299.99, 2000.00, 1800.00, 'INV-SG-P1001-001'),
('OI-2024-012-02', 'ORD-2024-012', 'P-1004', 'PV-1004-01', 30, 89.75, 200.00, 292.50, 'INV-EU-P1004-001');

-- 24. returns
INSERT INTO returns (return_id, order_id, product_id, variant_id, quantity, reason, return_status, returned_at, refund_amount, restocking_fee, inspection_notes) VALUES
('RET-2024-001', 'ORD-2024-002', 'P-1002', 'PV-1002-01', 1, 'Screen has dead pixels', 'refunded', '2024-02-20 10:00:00', 349.50, 0.00, 'Confirmed dead pixel cluster in upper right. Full refund issued.'),
('RET-2024-002', 'ORD-2024-003', 'P-1004', 'PV-1004-01', 2, 'Wrong size ordered', 'refunded', '2024-03-15 14:30:00', 159.50, 20.00, 'Units in perfect condition, restocked after inspection.'),
('RET-2024-003', 'ORD-2024-007', 'P-1003', 'PV-1003-01', 1, 'Does not fit comfortably', 'received', '2024-05-18 09:00:00', 119.99, 10.00, 'Awaiting inspection.'),
('RET-2024-004', 'ORD-2024-006', 'P-1006', 'PV-1006-01', 1, 'Camera malfunction during first flight', 'inspected', '2024-04-25 16:00:00', 899.00, 0.00, 'Confirmed camera gimbal defect. Warranty replacement approved.');

-- ============================================
-- DOMAIN 3: LOGISTICS (continued - shipments, customs)
-- ============================================

-- 25. shipments
INSERT INTO shipments (shipment_id, order_id, from_warehouse_id, to_customer_id, partner_id, status, shipped_at, estimated_delivery, actual_delivery, tracking_number, shipping_cost) VALUES
('SHP-2024-001', 'ORD-2024-001', 'WH-US-01', 'CUST-001', 'DP-001', 'delivered', '2024-01-21 08:00:00', '2024-01-25', '2024-01-24 14:30:00', 'FDX-US-78945612301', 25.50),
('SHP-2024-002', 'ORD-2024-002', 'WH-JP-01', 'CUST-002', 'DP-003', 'delivered', '2024-02-06 10:00:00', '2024-02-14', '2024-02-13 11:00:00', 'DHL-JP-45678901234', 45.00),
('SHP-2024-003', 'ORD-2024-003', 'WH-EU-01', 'CUST-004', 'DP-001', 'delivered', '2024-03-01 06:00:00', '2024-03-03', '2024-03-02 18:00:00', 'FDX-EU-12345678901', 65.00),
('SHP-2024-004', 'ORD-2024-004', 'WH-JP-01', 'CUST-003', 'DP-005', 'delivered', '2024-03-11 09:00:00', '2024-03-13', '2024-03-12 15:00:00', 'JPL-JP-98765432100', 12.50),
('SHP-2024-005', 'ORD-2024-005', 'WH-SG-01', 'CUST-005', 'DP-002', 'in_transit', '2024-03-27 07:00:00', '2024-04-15', NULL, 'MSK-SG-55566677788', 420.00),
('SHP-2024-006', 'ORD-2024-006', 'WH-SG-01', 'CUST-006', 'DP-004', 'delivered', '2024-04-12 14:00:00', '2024-04-13', '2024-04-12 18:30:00', 'GRB-SG-11122233344', 8.50),
('SHP-2024-007', 'ORD-2024-007', 'WH-US-01', 'CUST-007', 'DP-001', 'delivered', '2024-05-02 11:00:00', '2024-05-06', '2024-05-05 16:00:00', 'FDX-US-33344455566', 18.00),
('SHP-2024-008', 'ORD-2024-009', 'WH-SG-01', 'CUST-009', 'DP-004', 'in_transit', '2024-06-17 08:00:00', '2024-06-22', NULL, 'GRB-SG-77788899900', 35.00),
('SHP-2024-009', 'ORD-2024-011', 'WH-US-01', 'CUST-001', 'DP-001', 'delivered', '2024-08-11 09:00:00', '2024-08-14', '2024-08-13 12:00:00', 'FDX-US-99900011122', 32.00),
('SHP-2024-010', 'ORD-2024-012', 'WH-SG-01', 'CUST-006', 'DP-004', 'delivered', '2024-09-06 10:00:00', '2024-09-07', '2024-09-06 17:45:00', 'GRB-SG-22233344455', 15.00);

-- 26. customs_documentation
INSERT INTO customs_documentation (customs_id, shipment_id, document_type, document_url, hs_code, declared_value, duties_paid, verified, verified_by, verified_at) VALUES
('CUS-2024-001', 'SHP-2024-002', 'commercial_invoice', 'https://docs.company.com/customs/CI-2024-002.pdf', '8471.30.0100', 349.50, 52.43, TRUE, 'EMP-007', '2024-02-06 09:00:00'),
('CUS-2024-002', 'SHP-2024-002', 'packing_list', 'https://docs.company.com/customs/PL-2024-002.pdf', '8471.30.0100', 349.50, 0.00, TRUE, 'EMP-007', '2024-02-06 09:15:00'),
('CUS-2024-003', 'SHP-2024-003', 'commercial_invoice', 'https://docs.company.com/customs/CI-2024-003.pdf', '8518.30.2000', 5390.00, 485.10, TRUE, 'EMP-007', '2024-02-28 18:00:00'),
('CUS-2024-004', 'SHP-2024-003', 'certificate_of_origin', 'https://docs.company.com/customs/CO-2024-003.pdf', '8518.30.2000', 5390.00, 0.00, TRUE, 'EMP-007', '2024-02-28 18:30:00'),
('CUS-2024-005', 'SHP-2024-005', 'commercial_invoice', 'https://docs.company.com/customs/CI-2024-005.pdf', '8471.30.0100', 28750.00, 2587.50, TRUE, 'EMP-007', '2024-03-26 16:00:00'),
('CUS-2024-006', 'SHP-2024-005', 'packing_list', 'https://docs.company.com/customs/PL-2024-005.pdf', '8471.30.0100', 28750.00, 0.00, TRUE, 'EMP-007', '2024-03-26 16:30:00'),
('CUS-2024-007', 'SHP-2024-005', 'certificate_of_origin', 'https://docs.company.com/customs/CO-2024-005.pdf', '8471.30.0100', 28750.00, 0.00, FALSE, NULL, NULL),
('CUS-2024-008', 'SHP-2024-008', 'commercial_invoice', 'https://docs.company.com/customs/CI-2024-008.pdf', '8471.30.0100', 19500.00, 975.00, TRUE, 'EMP-006', '2024-06-16 17:00:00');

-- ============================================
-- DOMAIN 5: ANALYTICS
-- ============================================

-- 27. campaigns
INSERT INTO campaigns (campaign_id, campaign_name, channel, budget, start_date, end_date, target_countries, target_segments, status, campaign_manager) VALUES
('CMP-2024-001', 'Q1 Laptop Launch', 'search', 50000.00, '2024-01-01', '2024-03-31', '["US", "UK", "DE", "SG"]', '["retail", "corporate"]', 'completed', 'Akira Tanaka'),
('CMP-2024-002', 'SEA Solar Tablet Push', 'social', 25000.00, '2024-02-01', '2024-04-30', '["SG", "MY", "TH", "VN", "PH"]', '["retail"]', 'completed', 'Akira Tanaka'),
('CMP-2024-003', 'Spring Audio Sale', 'email', 15000.00, '2024-03-15', '2024-04-15', '["US", "UK", "AU"]', '["retail", "wholesale"]', 'completed', 'Akira Tanaka'),
('CMP-2024-004', 'Corporate Wearables Program', 'email', 30000.00, '2024-04-01', '2024-06-30', '["DE", "FR", "UK", "JP"]', '["corporate"]', 'completed', 'Akira Tanaka'),
('CMP-2024-005', 'Summer Accessories Bundle', 'display', 20000.00, '2024-06-01', '2024-08-31', '["US", "CA", "AU"]', '["retail"]', 'completed', 'Akira Tanaka'),
('CMP-2024-006', 'Drone Enthusiast Campaign', 'affiliate', 35000.00, '2024-07-01', '2024-09-30', '["US", "UK", "DE"]', '["retail"]', 'completed', 'Akira Tanaka'),
('CMP-2024-007', 'Holiday Season 2024', 'search', 75000.00, '2024-11-01', '2024-12-31', '["US", "UK", "DE", "JP", "SG", "AU"]', '["retail", "corporate", "wholesale"]', 'active', 'Akira Tanaka'),
('CMP-2025-001', 'New Year Tech Refresh', 'social', 40000.00, '2025-01-05', '2025-02-28', '["US", "SG", "JP"]', '["retail", "corporate"]', 'active', 'Akira Tanaka');

-- 28. website_sessions
INSERT INTO website_sessions (session_id, customer_id, entry_page, exit_page, session_duration_seconds, device_type, browser, country, region, session_start, bounce_rate) VALUES
('SESS-2024-00001', 'CUST-001', '/products/laptop-pro', '/checkout/confirm', 420, 'desktop', 'Chrome', 'USA', 'NA', '2024-01-20 10:15:00', FALSE),
('SESS-2024-00002', 'CUST-002', '/products/solar-tablet', '/checkout/confirm', 350, 'mobile', 'Safari', 'India', 'IN', '2024-02-05 13:30:00', FALSE),
('SESS-2024-00003', NULL, '/homepage', '/products/headphones', 90, 'mobile', 'Chrome', 'UK', 'EU', '2024-02-10 18:00:00', FALSE),
('SESS-2024-00004', 'CUST-004', '/products/wearables', '/checkout/confirm', 580, 'desktop', 'Firefox', 'Germany', 'EU', '2024-02-28 09:00:00', FALSE),
('SESS-2024-00005', NULL, '/homepage', '/homepage', 12, 'mobile', 'Safari', 'Brazil', 'SA', '2024-03-01 22:00:00', TRUE),
('SESS-2024-00006', 'CUST-005', '/products/laptop-pro', '/checkout/confirm', 720, 'desktop', 'Edge', 'France', 'EU', '2024-03-25 10:30:00', FALSE),
('SESS-2024-00007', 'CUST-007', '/products/headphones', '/checkout/confirm', 185, 'tablet', 'Safari', 'USA', 'NA', '2024-05-01 20:00:00', FALSE),
('SESS-2024-00008', NULL, '/blog/drone-reviews', '/products/drone', 240, 'desktop', 'Chrome', 'Canada', 'NA', '2024-05-15 15:00:00', FALSE),
('SESS-2024-00009', 'CUST-006', '/products/laptop-pro', '/checkout/confirm', 300, 'desktop', 'Chrome', 'Singapore', 'SEA', '2024-04-12 08:15:00', FALSE),
('SESS-2024-00010', NULL, '/homepage', '/products/accessories', 45, 'mobile', 'Samsung', 'South Korea', 'KR', '2024-06-01 19:00:00', FALSE),
('SESS-2024-00011', 'CUST-010', '/products/headphones', '/cart', 160, 'mobile', 'Chrome', 'Italy', 'EU', '2024-07-01 12:15:00', FALSE),
('SESS-2024-00012', 'CUST-001', '/products/laptop-pro', '/checkout/confirm', 210, 'desktop', 'Chrome', 'USA', 'NA', '2024-08-10 10:45:00', FALSE),
('SESS-2024-00013', NULL, '/homepage', '/homepage', 8, 'mobile', 'Safari', 'Mexico', 'NA', '2024-09-20 11:00:00', TRUE),
('SESS-2024-00014', 'CUST-008', '/products/drone', '/cart', 480, 'desktop', 'Firefox', 'Australia', 'AU', '2024-05-19 02:30:00', FALSE),
('SESS-2024-00015', 'CUST-009', '/products/laptop-pro', '/checkout/confirm', 600, 'desktop', 'Chrome', 'Malaysia', 'SEA', '2024-06-15 09:30:00', FALSE);

-- 29. conversion_funnels (GENERATED: conversion_rate)
INSERT INTO conversion_funnels (funnel_id, campaign_id, stage_name, stage_order, visitors_count, conversions_count, avg_time_to_convert_hours, notes) VALUES
-- Q1 Laptop Launch funnel
('FNL-CMP001-01', 'CMP-2024-001', 'Ad Impression', 1, 150000, 12000, NULL, 'Search ads across Google and Bing'),
('FNL-CMP001-02', 'CMP-2024-001', 'Landing Page Visit', 2, 12000, 4500, 0.10, 'Product page visits'),
('FNL-CMP001-03', 'CMP-2024-001', 'Add to Cart', 3, 4500, 1200, 2.50, 'Users adding laptop to cart'),
('FNL-CMP001-04', 'CMP-2024-001', 'Purchase', 4, 1200, 320, 12.00, 'Completed purchases'),
-- SEA Solar Tablet funnel
('FNL-CMP002-01', 'CMP-2024-002', 'Ad Impression', 1, 80000, 6400, NULL, 'Facebook and Instagram ads'),
('FNL-CMP002-02', 'CMP-2024-002', 'Landing Page Visit', 2, 6400, 2100, 0.05, NULL),
('FNL-CMP002-03', 'CMP-2024-002', 'Add to Cart', 3, 2100, 480, 1.80, NULL),
('FNL-CMP002-04', 'CMP-2024-002', 'Purchase', 4, 480, 95, 8.00, NULL),
-- Spring Audio Sale funnel
('FNL-CMP003-01', 'CMP-2024-003', 'Email Sent', 1, 45000, 9000, NULL, 'Email campaign'),
('FNL-CMP003-02', 'CMP-2024-003', 'Email Opened', 2, 9000, 3600, 2.00, NULL),
('FNL-CMP003-03', 'CMP-2024-003', 'Click Through', 3, 3600, 1100, 0.50, NULL),
('FNL-CMP003-04', 'CMP-2024-003', 'Purchase', 4, 1100, 180, 24.00, NULL),
-- Holiday Season funnel
('FNL-CMP007-01', 'CMP-2024-007', 'Ad Impression', 1, 500000, 45000, NULL, 'Global search campaign'),
('FNL-CMP007-02', 'CMP-2024-007', 'Landing Page Visit', 2, 45000, 15000, 0.08, NULL),
('FNL-CMP007-03', 'CMP-2024-007', 'Add to Cart', 3, 15000, 4500, 3.00, NULL),
('FNL-CMP007-04', 'CMP-2024-007', 'Purchase', 4, 4500, 1200, 18.00, 'Holiday season strong conversion');

-- 30. customer_lifetime_value
INSERT INTO customer_lifetime_value (clv_id, customer_id, calculated_clv, calculation_date, time_horizon, purchase_frequency, avg_order_value, predicted_churn_probability, segment) VALUES
('CLV-CUST001-2024Q2', 'CUST-001', 4800.00, '2024-06-30', '2_year', 2.50, 1250.00, 0.150, 'high_value'),
('CLV-CUST002-2024Q2', 'CUST-002', 1200.00, '2024-06-30', '2_year', 1.20, 430.00, 0.400, 'medium_value'),
('CLV-CUST003-2024Q2', 'CUST-003', 2500.00, '2024-06-30', '2_year', 1.80, 350.00, 0.250, 'medium_value'),
('CLV-CUST004-2024Q2', 'CUST-004', 25000.00, '2024-06-30', '3_year', 4.00, 5400.00, 0.080, 'enterprise'),
('CLV-CUST005-2024Q2', 'CUST-005', 65000.00, '2024-06-30', '3_year', 3.50, 28750.00, 0.050, 'enterprise'),
('CLV-CUST006-2024Q2', 'CUST-006', 85000.00, '2024-06-30', 'lifetime', 6.00, 21050.00, 0.030, 'enterprise'),
('CLV-CUST007-2024Q2', 'CUST-007', 800.00, '2024-06-30', '1_year', 1.00, 180.00, 0.550, 'low_value'),
('CLV-CUST008-2024Q2', 'CUST-008', 15000.00, '2024-06-30', '2_year', 2.00, 2700.00, 0.200, 'high_value'),
('CLV-CUST009-2024Q2', 'CUST-009', 45000.00, '2024-06-30', '3_year', 3.00, 19500.00, 0.100, 'enterprise'),
('CLV-CUST010-2024Q2', 'CUST-010', 350.00, '2024-06-30', '1_year', 0.50, 130.00, 0.700, 'at_risk');

-- 31. demand_forecasts
INSERT INTO demand_forecasts (forecast_id, product_id, variant_id, forecast_date, forecasted_quantity, confidence_interval_lower, confidence_interval_upper, method, created_at, accuracy_score) VALUES
('DF-P1001-PV01-2024Q3', 'P-1001', 'PV-1001-01', '2024-09-30', 450, 380, 520, 'ensemble', '2024-07-01 00:00:00', 0.8800),
('DF-P1001-PV01-2024Q4', 'P-1001', 'PV-1001-01', '2024-12-31', 600, 500, 700, 'prophet', '2024-07-01 00:00:00', 0.8500),
('DF-P1002-PV01-2024Q3', 'P-1002', 'PV-1002-01', '2024-09-30', 200, 150, 250, 'arima', '2024-07-01 00:00:00', 0.7900),
('DF-P1003-PV01-2024Q3', 'P-1003', 'PV-1003-01', '2024-09-30', 800, 700, 900, 'ensemble', '2024-07-01 00:00:00', 0.9200),
('DF-P1003-PV01-2024Q4', 'P-1003', 'PV-1003-01', '2024-12-31', 1200, 1000, 1400, 'prophet', '2024-07-01 00:00:00', 0.8700),
('DF-P1004-PV01-2024Q3', 'P-1004', 'PV-1004-01', '2024-09-30', 350, 280, 420, 'exponential_smoothing', '2024-07-01 00:00:00', 0.8100),
('DF-P1005-PV01-2024Q3', 'P-1005', 'PV-1005-01', '2024-09-30', 1500, 1300, 1700, 'arima', '2024-07-01 00:00:00', 0.9000),
('DF-P1006-PV01-2024Q3', 'P-1006', 'PV-1006-01', '2024-09-30', 80, 50, 110, 'ensemble', '2024-07-01 00:00:00', 0.7200),
('DF-P1001-PV01-2025Q1', 'P-1001', 'PV-1001-01', '2025-03-31', 500, 420, 580, 'prophet', '2024-10-01 00:00:00', 0.8300),
('DF-P1003-PV01-2025Q1', 'P-1003', 'PV-1003-01', '2025-03-31', 900, 780, 1020, 'ensemble', '2024-10-01 00:00:00', 0.9100);

-- ============================================
-- DOMAIN 6: FINANCE
-- ============================================

-- 32. transactions
INSERT INTO transactions (transaction_id, order_id, transaction_type, amount, currency, fx_rate, transaction_date, status, payment_gateway, settlement_date) VALUES
('TXN-2024-001', 'ORD-2024-001', 'sale', 1299.99, 'USD', 1.0000, '2024-01-20 10:31:00', 'completed', 'Stripe', '2024-01-22'),
('TXN-2024-002', 'ORD-2024-002', 'sale', 429.50, 'USD', 1.0000, '2024-02-05 14:01:00', 'completed', 'Razorpay', '2024-02-08'),
('TXN-2024-003', 'ORD-2024-002', 'refund', -349.50, 'USD', 1.0000, '2024-02-22 11:00:00', 'completed', 'Razorpay', '2024-02-25'),
('TXN-2024-004', 'ORD-2024-003', 'sale', 5390.00, 'EUR', 1.0850, '2024-02-28 09:16:00', 'completed', 'Adyen', '2024-03-02'),
('TXN-2024-005', 'ORD-2024-004', 'sale', 349.50, 'JPY', 0.0067, '2024-03-10 16:46:00', 'completed', 'Stripe', '2024-03-13'),
('TXN-2024-006', 'ORD-2024-005', 'sale', 28750.00, 'EUR', 1.0900, '2024-03-25 11:01:00', 'completed', 'Adyen', '2024-03-28'),
('TXN-2024-007', 'ORD-2024-006', 'sale', 8499.00, 'SGD', 0.7400, '2024-04-12 08:31:00', 'completed', 'Stripe', '2024-04-15'),
('TXN-2024-008', 'ORD-2024-007', 'sale', 179.98, 'USD', 1.0000, '2024-05-01 20:16:00', 'completed', 'PayPal', '2024-05-04'),
('TXN-2024-009', 'ORD-2024-008', 'sale', 2699.00, 'AUD', 0.6500, '2024-05-20 03:01:00', 'pending', 'Stripe', NULL),
('TXN-2024-010', 'ORD-2024-009', 'sale', 19500.00, 'MYR', 0.2150, '2024-06-15 09:46:00', 'completed', 'Adyen', '2024-06-18'),
('TXN-2024-011', 'ORD-2024-010', 'sale', 129.99, 'EUR', 1.0800, '2024-07-01 12:31:00', 'reversed', 'Stripe', NULL),
('TXN-2024-012', 'ORD-2024-011', 'sale', 1199.99, 'USD', 1.0000, '2024-08-10 11:01:00', 'completed', 'Stripe', '2024-08-13'),
('TXN-2024-013', 'ORD-2024-012', 'sale', 33600.00, 'SGD', 0.7450, '2024-09-05 14:21:00', 'completed', 'Stripe', '2024-09-08'),
('TXN-2024-014', 'ORD-2024-003', 'refund', -159.50, 'EUR', 1.0850, '2024-03-18 10:00:00', 'completed', 'Adyen', '2024-03-21'),
('TXN-2024-015', 'ORD-2024-006', 'fee', -25.00, 'SGD', 0.7400, '2024-04-30 00:00:00', 'completed', 'Stripe', '2024-04-30');

-- 33. invoices
INSERT INTO invoices (invoice_id, order_id, invoice_date, due_date, total_amount, paid_amount, status, payment_terms, late_fee_applied, last_reminder_sent) VALUES
('INV-2024-001', 'ORD-2024-001', '2024-01-20', '2024-02-19', 1299.99, 1299.99, 'paid', 'Net 30', 0.00, NULL),
('INV-2024-002', 'ORD-2024-002', '2024-02-05', '2024-03-07', 429.50, 429.50, 'paid', 'Net 30', 0.00, NULL),
('INV-2024-003', 'ORD-2024-003', '2024-02-28', '2024-03-29', 5390.00, 5390.00, 'paid', 'Net 30', 0.00, NULL),
('INV-2024-004', 'ORD-2024-004', '2024-03-10', '2024-04-09', 349.50, 349.50, 'paid', 'Net 30', 0.00, NULL),
('INV-2024-005', 'ORD-2024-005', '2024-03-25', '2024-05-24', 28750.00, 28750.00, 'paid', 'Net 60', 0.00, NULL),
('INV-2024-006', 'ORD-2024-006', '2024-04-12', '2024-04-27', 8499.00, 8499.00, 'paid', 'Net 15', 0.00, NULL),
('INV-2024-007', 'ORD-2024-007', '2024-05-01', '2024-05-31', 179.98, 179.98, 'paid', 'Net 30', 0.00, NULL),
('INV-2024-008', 'ORD-2024-008', '2024-05-20', '2024-06-19', 2699.00, 0.00, 'overdue', 'Net 30', 45.00, '2024-06-25'),
('INV-2024-009', 'ORD-2024-009', '2024-06-15', '2024-08-14', 19500.00, 19500.00, 'paid', 'Net 60', 0.00, NULL),
('INV-2024-010', 'ORD-2024-011', '2024-08-10', '2024-09-09', 1199.99, 1199.99, 'paid', 'Net 30', 0.00, NULL),
('INV-2024-011', 'ORD-2024-012', '2024-09-05', '2024-10-05', 33600.00, 33600.00, 'paid', 'Net 30', 0.00, NULL);

-- 34. cost_allocations
INSERT INTO cost_allocations (allocation_id, product_id, campaign_id, cost_center, amount, allocation_method, period_start, period_end, allocated_by) VALUES
('CA-2024-001', 'P-1001', 'CMP-2024-001', 'CC-005', 20000.00, 'direct', '2024-01-01', '2024-03-31', 'EMP-009'),
('CA-2024-002', 'P-1002', 'CMP-2024-002', 'CC-005', 25000.00, 'direct', '2024-02-01', '2024-04-30', 'EMP-009'),
('CA-2024-003', 'P-1003', 'CMP-2024-003', 'CC-005', 15000.00, 'direct', '2024-03-15', '2024-04-15', 'EMP-009'),
('CA-2024-004', 'P-1004', 'CMP-2024-004', 'CC-005', 18000.00, 'proportional', '2024-04-01', '2024-06-30', 'EMP-009'),
('CA-2024-005', 'P-1003', 'CMP-2024-004', 'CC-005', 12000.00, 'proportional', '2024-04-01', '2024-06-30', 'EMP-009'),
('CA-2024-006', 'P-1005', 'CMP-2024-005', 'CC-005', 10000.00, 'direct', '2024-06-01', '2024-08-31', 'EMP-009'),
('CA-2024-007', 'P-1003', 'CMP-2024-005', 'CC-005', 10000.00, 'proportional', '2024-06-01', '2024-08-31', 'EMP-009'),
('CA-2024-008', 'P-1006', 'CMP-2024-006', 'CC-005', 35000.00, 'direct', '2024-07-01', '2024-09-30', 'EMP-009'),
('CA-2024-009', 'P-1001', 'CMP-2024-007', 'CC-005', 25000.00, 'activity_based', '2024-11-01', '2024-12-31', 'EMP-009'),
('CA-2024-010', 'P-1003', 'CMP-2024-007', 'CC-005', 20000.00, 'activity_based', '2024-11-01', '2024-12-31', 'EMP-009'),
('CA-2024-011', 'P-1004', 'CMP-2024-007', 'CC-005', 15000.00, 'activity_based', '2024-11-01', '2024-12-31', 'EMP-009'),
('CA-2024-012', 'P-1005', 'CMP-2024-007', 'CC-005', 15000.00, 'activity_based', '2024-11-01', '2024-12-31', 'EMP-009');

-- 35. profitability_analysis (GENERATED: net_profit, margin_percentage)
INSERT INTO profitability_analysis (analysis_id, product_id, variant_id, period, revenue, cost_of_goods_sold, operating_expenses, shipping_costs, marketing_costs, currency) VALUES
('PA-P1001-PV01-2024-01', 'P-1001', 'PV-1001-01', '2024-01', 25999.80, 17999.80, 3200.00, 510.00, 6666.67, 'USD'),
('PA-P1001-PV01-2024-02', 'P-1001', 'PV-1001-01', '2024-02', 38999.70, 26999.70, 4800.00, 765.00, 6666.67, 'USD'),
('PA-P1001-PV01-2024-03', 'P-1001', 'PV-1001-01', '2024-03', 51999.60, 35999.60, 6400.00, 1020.00, 6666.66, 'USD'),
('PA-P1002-PV01-2024-02', 'P-1002', 'PV-1002-01', '2024-02', 10485.00, 5242.50, 1200.00, 450.00, 8333.33, 'USD'),
('PA-P1002-PV01-2024-03', 'P-1002', 'PV-1002-01', '2024-03', 13980.00, 6990.00, 1600.00, 600.00, 8333.33, 'USD'),
('PA-P1003-PV01-2024-01', 'P-1003', 'PV-1003-01', '2024-01', 6499.50, 3249.75, 800.00, 180.00, 0.00, 'USD'),
('PA-P1003-PV01-2024-03', 'P-1003', 'PV-1003-01', '2024-03', 19498.50, 9749.25, 2400.00, 540.00, 5000.00, 'USD'),
('PA-P1003-PV01-2024-04', 'P-1003', 'PV-1003-01', '2024-04', 12999.00, 6499.50, 1600.00, 360.00, 5000.00, 'USD'),
('PA-P1004-PV01-2024-02', 'P-1004', 'PV-1004-01', '2024-02', 4487.50, 2243.75, 550.00, 130.00, 0.00, 'USD'),
('PA-P1004-PV01-2024-04', 'P-1004', 'PV-1004-01', '2024-04', 8975.00, 4487.50, 1100.00, 260.00, 6000.00, 'USD'),
('PA-P1005-PV01-2024-06', 'P-1005', 'PV-1005-01', '2024-06', 14997.00, 7498.50, 1800.00, 350.00, 3333.33, 'USD'),
('PA-P1006-PV01-2024-04', 'P-1006', 'PV-1006-01', '2024-04', 3596.00, 2396.00, 450.00, 85.00, 0.00, 'USD'),
('PA-P1006-PV01-2024-07', 'P-1006', 'PV-1006-01', '2024-07', 8990.00, 5990.00, 1100.00, 210.00, 11666.67, 'USD');

-- ============================================
-- END OF COMPLETE SAMPLE DATA
-- ============================================
