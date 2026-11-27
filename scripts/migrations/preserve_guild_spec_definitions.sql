-- Apply once to existing metastores after add_route_mark_forwarded.sql.
-- Re-save original guild specifications afterwards: previously discarded fields
-- and ordering cannot be inferred from the legacy rows.
ALTER TABLE guilds ADD COLUMN spec_data JSON;
ALTER TABLE agents ADD COLUMN spec_data JSON;
ALTER TABLE agents ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
ALTER TABLE guild_routes ADD COLUMN spec_data JSON;
ALTER TABLE guild_routes ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
