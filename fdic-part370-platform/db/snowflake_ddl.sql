-- ============================================================================
-- FDIC Part 370 Insurance Determination Platform — Snowflake DDL
-- Database/schema convention: FDIC_PART370.CORE
-- ============================================================================
CREATE DATABASE IF NOT EXISTS FDIC_PART370;
CREATE SCHEMA IF NOT EXISTS FDIC_PART370.CORE;
USE SCHEMA FDIC_PART370.CORE;

-- ---------------------------------------------------------------------------
-- CUSTOMER
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CUSTOMER (
    CUSTOMER_ID     STRING       NOT NULL,
    FIRST_NAME      STRING,
    LAST_NAME       STRING,
    SSN_TIN         STRING,                 -- store encrypted/tokenized in prod
    CUSTOMER_TYPE   STRING,
    ADDRESS         STRING,
    EMAIL           STRING,
    PHONE           STRING,
    CREATED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
) CLUSTER BY (CUSTOMER_ID);

-- ---------------------------------------------------------------------------
-- ACCOUNT
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ACCOUNT (
    ACCOUNT_NUMBER     STRING        NOT NULL,
    CUSTOMER_ID        STRING        NOT NULL,
    PRODUCT_TYPE       STRING,
    BALANCE            NUMBER(18,2)  DEFAULT 0,
    ACCRUED_INTEREST   NUMBER(18,2)  DEFAULT 0,
    HOLD_AMOUNT        NUMBER(18,2)  DEFAULT 0,
    ORC                STRING        NOT NULL,
    CREATED_AT         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_ACCOUNT PRIMARY KEY (ACCOUNT_NUMBER),
    CONSTRAINT FK_ACCOUNT_CUSTOMER FOREIGN KEY (CUSTOMER_ID) REFERENCES CUSTOMER(CUSTOMER_ID)
) CLUSTER BY (CUSTOMER_ID, ORC);

CREATE INDEX IF NOT EXISTS IX_ACCOUNT_ORC ON ACCOUNT(ORC);

-- ---------------------------------------------------------------------------
-- ACCOUNT_PARTICIPANT  (owners / beneficiaries / participants / mortgagors)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ACCOUNT_PARTICIPANT (
    PARTICIPANT_ID   STRING        NOT NULL DEFAULT UUID_STRING(),
    ACCOUNT_NUMBER   STRING        NOT NULL,
    PARTY_ID         STRING        NOT NULL,
    PARTY_ROLE       STRING        NOT NULL,  -- OWNER | BENEFICIARY | PARTICIPANT
    NAME             STRING,
    INTEREST_PCT     NUMBER(9,4)   DEFAULT 0,
    VESTED_INTEREST  NUMBER(18,2)  DEFAULT 0,
    CONSTRAINT PK_PARTICIPANT PRIMARY KEY (PARTICIPANT_ID),
    CONSTRAINT FK_PART_ACCOUNT FOREIGN KEY (ACCOUNT_NUMBER) REFERENCES ACCOUNT(ACCOUNT_NUMBER)
) CLUSTER BY (ACCOUNT_NUMBER);

-- ---------------------------------------------------------------------------
-- PENDING
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PENDING (
    PENDING_ID       STRING        NOT NULL DEFAULT UUID_STRING(),
    DETERMINATION_ID STRING        NOT NULL,
    ACCOUNT_NUMBER   STRING,
    CUSTOMER_ID      STRING,
    REASON_CODE      STRING        NOT NULL,  -- A,B,OI,RAC,ARB,ARBN,ARCRA,AREBP,ARM,ARO,ARTR
    DETAIL           STRING,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_PENDING PRIMARY KEY (PENDING_ID)
) CLUSTER BY (DETERMINATION_ID, REASON_CODE);

-- ---------------------------------------------------------------------------
-- INSURANCE_RESULT
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS INSURANCE_RESULT (
    DETERMINATION_ID STRING        NOT NULL,
    CUSTOMER_ID      STRING        NOT NULL,
    ORC              STRING,
    AGGREGATED_PI    NUMBER(18,2),
    COVERAGE_LIMIT   NUMBER(18,2),
    INSURED_AMOUNT   NUMBER(18,2),
    UNINSURED_AMOUNT NUMBER(18,2),
    IS_RECALC        BOOLEAN       DEFAULT FALSE,
    SUMMARY_REPORT   VARIANT,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_INS_RESULT PRIMARY KEY (DETERMINATION_ID, ORC),
    CONSTRAINT FK_RESULT_CUSTOMER FOREIGN KEY (CUSTOMER_ID) REFERENCES CUSTOMER(CUSTOMER_ID)
) CLUSTER BY (DETERMINATION_ID);

-- ---------------------------------------------------------------------------
-- CALCULATION_AUDIT  (full evidence chain / agent trace)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CALCULATION_AUDIT (
    AUDIT_ID         STRING        NOT NULL DEFAULT UUID_STRING(),
    DETERMINATION_ID STRING        NOT NULL,
    PAYLOAD          VARIANT,                 -- full agent state / evidence
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_CALC_AUDIT PRIMARY KEY (AUDIT_ID)
) CLUSTER BY (DETERMINATION_ID);

-- ---------------------------------------------------------------------------
-- LANGSMITH_EVAL_RESULTS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS LANGSMITH_EVAL_RESULTS (
    EVAL_ID          STRING        NOT NULL DEFAULT UUID_STRING(),
    DETERMINATION_ID STRING,
    EVAL_NAME        STRING        NOT NULL,
    STATUS           STRING        NOT NULL,  -- PASS | FAIL | WARNING
    DETAIL           STRING,
    LANGSMITH_RUN_ID STRING,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_EVAL PRIMARY KEY (EVAL_ID)
) CLUSTER BY (DETERMINATION_ID, EVAL_NAME);
