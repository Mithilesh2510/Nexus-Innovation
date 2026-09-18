-- =============================================================================
-- Healthcare Supply Chain Intelligence Database Schema
-- Target: MySQL 8.0+
-- Database: supply_chain_db
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `supply_chain_db`
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE `supply_chain_db`;

SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 1. Branches (Hospital Locations / Warehouses)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `branches`;
CREATE TABLE `branches` (
    `branch_id` VARCHAR(10) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `type` VARCHAR(50) NOT NULL,
    PRIMARY KEY (`branch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 2. Suppliers (Vendor Master & Performance Metrics)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `suppliers`;
CREATE TABLE `suppliers` (
    `supplier_id` VARCHAR(10) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `avg_lead_time_days` DECIMAL(6, 2) NOT NULL,
    `lead_time_std_days` DECIMAL(6, 2) NOT NULL,
    `reliability_score` DECIMAL(4, 2) NOT NULL,
    PRIMARY KEY (`supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3. Medicines (SKU Master & Policy Thresholds)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `medicines`;
CREATE TABLE `medicines` (
    `medicine_id` VARCHAR(20) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `category` VARCHAR(100) NOT NULL,
    `criticality` ENUM('Critical', 'High', 'Medium', 'Low') NOT NULL,
    `base_daily_usage` DECIMAL(10, 2) NOT NULL,
    `reorder_point` DECIMAL(10, 2) NOT NULL,
    `target_max_stock` DECIMAL(10, 2) NOT NULL,
    `shelf_life_days` INT NOT NULL,
    `unit_cost` DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (`medicine_id`),
    KEY `idx_med_category` (`category`),
    KEY `idx_med_criticality` (`criticality`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 4. Consumption History (Daily Unit Consumption by SKU and Branch)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `consumption_history`;
CREATE TABLE `consumption_history` (
    `id` BIGINT AUTO_INCREMENT NOT NULL,
    `date` DATE NOT NULL,
    `medicine_id` VARCHAR(20) NOT NULL,
    `branch_id` VARCHAR(10) NOT NULL,
    `units_consumed` DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_ch_med_branch_date` (`medicine_id`, `branch_id`, `date`),
    KEY `idx_ch_date` (`date`),
    KEY `idx_ch_med_date` (`medicine_id`, `date`),
    CONSTRAINT `fk_ch_medicine` FOREIGN KEY (`medicine_id`) REFERENCES `medicines` (`medicine_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ch_branch` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`branch_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 5. Inventory Snapshot (Current Stock & Expiry per Branch)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `inventory_snapshot`;
CREATE TABLE `inventory_snapshot` (
    `id` INT AUTO_INCREMENT NOT NULL,
    `medicine_id` VARCHAR(20) NOT NULL,
    `branch_id` VARCHAR(10) NOT NULL,
    `current_stock` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    `reserved_units` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    `emergency_reserve` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    `nearest_batch_expiry` DATE NOT NULL,
    `snapshot_date` DATE NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inv_med_branch` (`medicine_id`, `branch_id`),
    CONSTRAINT `fk_inv_medicine` FOREIGN KEY (`medicine_id`) REFERENCES `medicines` (`medicine_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_inv_branch` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`branch_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 6. Procurement History (Purchase Orders & Deliveries)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `procurement_history`;
CREATE TABLE `procurement_history` (
    `order_id` VARCHAR(50) NOT NULL,
    `medicine_id` VARCHAR(20) NOT NULL,
    `supplier_id` VARCHAR(10) NOT NULL,
    `branch_id` VARCHAR(10) NULL,
    `medicine_name` VARCHAR(255) NULL,
    `order_date` DATE NOT NULL,
    `expected_delivery_date` DATE NOT NULL,
    `actual_delivery_date` DATE NULL,
    `ordered_units` INT NOT NULL,
    `received_units` INT NOT NULL DEFAULT 0,
    `status` VARCHAR(20) NOT NULL,
    `unit_cost` DECIMAL(10, 2) NULL,
    `total_cost` DECIMAL(12, 2) NULL,
    PRIMARY KEY (`order_id`),
    KEY `idx_ph_medicine` (`medicine_id`),
    KEY `idx_ph_supplier` (`supplier_id`),
    KEY `idx_ph_order_date` (`order_date`),
    KEY `idx_ph_status` (`status`),
    CONSTRAINT `fk_ph_medicine` FOREIGN KEY (`medicine_id`) REFERENCES `medicines` (`medicine_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ph_supplier` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`supplier_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 7. Supply Events (Supply Disruptions & Surges)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `supply_events`;
CREATE TABLE `supply_events` (
    `event_id` VARCHAR(20) NOT NULL,
    `date` DATE NOT NULL,
    `medicine_id` VARCHAR(20) NULL,
    `event_type` VARCHAR(50) NOT NULL,
    `description` TEXT NOT NULL,
    `magnitude` DECIMAL(6, 2) NOT NULL,
    PRIMARY KEY (`event_id`),
    KEY `idx_se_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 8. Usage Anomalies (Ground Truth Anomaly Labels)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `usage_anomalies`;
CREATE TABLE `usage_anomalies` (
    `id` INT AUTO_INCREMENT NOT NULL,
    `medicine_id` VARCHAR(20) NOT NULL,
    `branch_id` VARCHAR(10) NOT NULL,
    `date` DATE NOT NULL,
    `multiplier_vs_baseline` DECIMAL(6, 2) NOT NULL,
    `label` VARCHAR(50) NOT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_ua_med_branch` (`medicine_id`, `branch_id`),
    KEY `idx_ua_date` (`date`),
    CONSTRAINT `fk_ua_medicine` FOREIGN KEY (`medicine_id`) REFERENCES `medicines` (`medicine_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ua_branch` FOREIGN KEY (`branch_id`) REFERENCES `branches` (`branch_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 9. Dispatched Lateral Transfers (Audit Ledger of Inter-Branch Transfers)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `dispatched_transfers`;
CREATE TABLE `dispatched_transfers` (
    `transfer_id` VARCHAR(50) NOT NULL,
    `timestamp` DATETIME NOT NULL,
    `medicine_id` VARCHAR(20) NOT NULL,
    `medicine_name` VARCHAR(255) NOT NULL,
    `from_branch` VARCHAR(10) NOT NULL,
    `to_branch` VARCHAR(10) NOT NULL,
    `units` INT NOT NULL,
    `status` VARCHAR(50) NOT NULL DEFAULT 'IN_TRANSIT',
    PRIMARY KEY (`transfer_id`),
    KEY `idx_dt_medicine` (`medicine_id`),
    KEY `idx_dt_from_branch` (`from_branch`),
    KEY `idx_dt_to_branch` (`to_branch`),
    CONSTRAINT `fk_dt_medicine` FOREIGN KEY (`medicine_id`) REFERENCES `medicines` (`medicine_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_dt_from_branch` FOREIGN KEY (`from_branch`) REFERENCES `branches` (`branch_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_dt_to_branch` FOREIGN KEY (`to_branch`) REFERENCES `branches` (`branch_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

