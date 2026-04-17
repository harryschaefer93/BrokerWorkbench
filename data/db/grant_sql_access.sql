-- ============================================================
-- Grant backend managed identity access to Azure SQL Database
-- ============================================================
-- Run this script in the Azure SQL database (sqldb-brokerworkbench-dev)
-- as the AAD admin user BEFORE running database_setup.py --target azure-sql.
--
-- Connect via:
--   - Azure Portal > SQL Database > Query Editor (preview)
--   - sqlcmd with AAD auth through the private endpoint
--
-- The managed identity must already exist in Azure AD.
-- ============================================================

-- Create database user for the backend managed identity
CREATE USER [id-backend-brokerworkbench-dev] FROM EXTERNAL PROVIDER;

-- Grant read/write access
ALTER ROLE db_datareader ADD MEMBER [id-backend-brokerworkbench-dev];
ALTER ROLE db_datawriter ADD MEMBER [id-backend-brokerworkbench-dev];

-- Grant DDL admin so the app can create/alter tables via database_setup.py
-- (Revoke this role after initial schema setup if desired)
ALTER ROLE db_ddladmin ADD MEMBER [id-backend-brokerworkbench-dev];

-- ============================================================
-- Create the two schemas for master + transactional data
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'master_data')
    EXEC('CREATE SCHEMA master_data');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'txn')
    EXEC('CREATE SCHEMA txn');
GO

-- Grant the managed identity usage on both schemas
GRANT ALTER, SELECT, INSERT, UPDATE, DELETE ON SCHEMA::master_data TO [id-backend-brokerworkbench-dev];
GRANT ALTER, SELECT, INSERT, UPDATE, DELETE ON SCHEMA::txn TO [id-backend-brokerworkbench-dev];
GO

PRINT 'Done — backend managed identity has been granted access.';
