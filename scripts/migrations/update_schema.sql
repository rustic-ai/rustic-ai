-- DDL to update database schema with new columns for Soft Delete and Status tracking

-- 1. Update agents table
-- Adding status column to track agent lifecycle (e.g., 'not_launched', 'running', 'deleted')
ALTER TABLE agents ADD COLUMN status VARCHAR DEFAULT 'not_launched';

-- 2. Update guild_routes table
-- Adding status column to track route lifecycle (e.g., 'active', 'deleted')
ALTER TABLE guild_routes ADD COLUMN status VARCHAR DEFAULT 'active';

-- Adding agent_type column to store the qualified class name of the target agent
ALTER TABLE guild_routes ADD COLUMN agent_type VARCHAR;

-- 3. Update guilds table
-- Adding status column to track overall guild health/status
ALTER TABLE guilds ADD COLUMN status VARCHAR DEFAULT 'unknown';
