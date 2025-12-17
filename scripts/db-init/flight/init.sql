-- =========================
-- Flight RM Init SQL
-- =========================

CREATE DATABASE IF NOT EXISTS rm_db;
USE rm_db;

CREATE TABLE IF NOT EXISTS FLIGHTS (
    flightNum VARCHAR(20) PRIMARY KEY,
    price INT NOT NULL,
    numSeats INT NOT NULL,
    numAvail INT NOT NULL
);
