-- =========================
-- Customer + Reservation RM Init SQL
-- =========================

CREATE DATABASE IF NOT EXISTS rm_db;
USE rm_db;

CREATE TABLE IF NOT EXISTS CUSTOMERS (
    custName VARCHAR(100) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS RESERVATIONS (
    custName VARCHAR(100),
    resvType ENUM('FLIGHT', 'HOTEL', 'CAR'),
    resvKey VARCHAR(100),
    PRIMARY KEY (custName, resvType, resvKey)
);
