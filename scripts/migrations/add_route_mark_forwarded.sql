-- Apply once to existing guild metastores before starting the updated application.
-- SQLModel.create_all creates new tables but does not add columns to existing ones.
-- The original flag was not stored, so existing routes retain the previous false
-- behavior. Re-save affected guild specifications to restore their intended flags.
ALTER TABLE guild_routes ADD COLUMN mark_forwarded BOOLEAN NOT NULL DEFAULT FALSE;
