-- MySQL Schema for Tap&Go Database
CREATE DATABASE IF NOT EXISTS tapgo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE tapgo;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_type VARCHAR(20) NOT NULL DEFAULT 'passenger',
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL UNIQUE,
    address TEXT NULL,
    city VARCHAR(100) NULL,
    pincode VARCHAR(10) NULL,
    aadhaar VARCHAR(20) NULL,
    pan VARCHAR(20) NULL,
    password_hash VARCHAR(255) NOT NULL,
    profile_photo VARCHAR(255) NULL,
    vehicle_type VARCHAR(50) NULL,
    vehicle_registration VARCHAR(50) NULL,
    vehicle_make VARCHAR(100) NULL,
    vehicle_model VARCHAR(100) NULL,
    driving_licence_number VARCHAR(50) NULL,
    rc_document VARCHAR(255) NULL,
    licence_document VARCHAR(255) NULL,
    insurance_document VARCHAR(255) NULL,
    signature_document VARCHAR(255) NULL,
    id_document VARCHAR(255) NULL,
    state VARCHAR(100) NULL,
    emergency_contact_name VARCHAR(100) NULL,
    emergency_contact_phone VARCHAR(20) NULL,
    bank_account_holder VARCHAR(100) NULL,
    bank_account_number VARCHAR(50) NULL,
    bank_ifsc VARCHAR(20) NULL,
    bank_upi_id VARCHAR(50) NULL,
    bank_locked INT DEFAULT 0,
    bank_request_status VARCHAR(20) DEFAULT 'none',
    doc_request_status VARCHAR(20) DEFAULT 'none',
    phone_request_status VARCHAR(20) DEFAULT 'none',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    qr_identifier VARCHAR(128) NULL,
    nfc_identifier VARCHAR(128) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX (email),
    INDEX (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL DEFAULT 'Tap&Go Administrator',
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS wallets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    balance DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    is_frozen BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS payment_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    wallet_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    upi_uri TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    provider VARCHAR(30) NOT NULL DEFAULT 'FAMPAY_TEST',
    provider_transaction_id VARCHAR(128) NULL,
    utr VARCHAR(128) NULL,
    payer_name VARCHAR(120) NULL,
    raw_email_id VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL,
    verified_at DATETIME NULL,
    last_checked_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (wallet_id) REFERENCES wallets(id),
    INDEX (user_id),
    INDEX (status),
    INDEX (utr)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reference VARCHAR(64) NOT NULL UNIQUE,
    passenger_id INT NULL,
    driver_id INT NULL,
    wallet_id INT NULL,
    amount DECIMAL(12,2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL DEFAULT 'wallet',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    otp_verified BOOLEAN NOT NULL DEFAULT FALSE,
    fraud_status VARCHAR(20) NOT NULL DEFAULT 'clear',
    transaction_type VARCHAR(30) NULL,
    description TEXT NULL,
    balance_after DECIMAL(12,2) NULL,
    idempotency_key VARCHAR(128) NULL UNIQUE,
    related_transaction_id INT NULL,
    provider VARCHAR(30) NULL,
    provider_transaction_id VARCHAR(128) NULL,
    utr VARCHAR(128) NULL,
    payer_name VARCHAR(120) NULL,
    payment_request_id INT NULL,
    payment_source VARCHAR(50) NULL,
    email_received_at DATETIME NULL,
    raw_email_id VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (passenger_id) REFERENCES users(id),
    FOREIGN KEY (driver_id) REFERENCES users(id),
    FOREIGN KEY (wallet_id) REFERENCES wallets(id),
    FOREIGN KEY (related_transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (payment_request_id) REFERENCES payment_requests(id),
    INDEX (reference),
    INDEX (passenger_id),
    INDEX (driver_id),
    INDEX (idempotency_key),
    INDEX (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    document_type VARCHAR(80) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS edit_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    previous_value TEXT NULL,
    new_value TEXT NULL,
    proof_path VARCHAR(255) NULL,
    reason TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_by INT NULL,
    reviewed_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES admins(id),
    INDEX (user_id),
    INDEX (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fraud_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    transaction_id INT NULL,
    risk_score INT NOT NULL DEFAULT 0,
    reason TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    INDEX (user_id),
    INDEX (transaction_id),
    INDEX (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS activity_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NULL,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    details TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admins(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX (admin_id),
    INDEX (user_id),
    INDEX (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS project_settings (
    `key` VARCHAR(100) PRIMARY KEY,
    value TEXT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS email_otps (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(120) NOT NULL,
    otp VARCHAR(10) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    INDEX (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
