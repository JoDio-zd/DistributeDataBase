-- =========================
-- Car RM Init SQL
-- =========================

CREATE DATABASE IF NOT EXISTS rm_db;
USE rm_db;

CREATE TABLE IF NOT EXISTS CARS (
    location VARCHAR(100) PRIMARY KEY,
    price INT NOT NULL,
    numCars INT NOT NULL,
    numAvail INT NOT NULL
);
