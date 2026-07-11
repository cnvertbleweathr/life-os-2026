-- Create append-only output tables for OpenClaw

CREATE TABLE IF NOT EXISTS raw.ai_cfb_narratives (
    narrative_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id INTEGER NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    narrative TEXT NOT NULL,
    token_count INTEGER,
    model VARCHAR DEFAULT 'claude-sonnet-4-6'
);

CREATE TABLE IF NOT EXISTS raw.ai_life_briefs (
    brief_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_date DATE NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    brief_type VARCHAR,
    brief_content TEXT NOT NULL,
    token_count INTEGER,
    model VARCHAR DEFAULT 'claude-sonnet-4-6'
);

CREATE TABLE IF NOT EXISTS raw.ai_habit_insights (
    insight_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_date DATE NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    habit_name VARCHAR,
    insight_content TEXT NOT NULL,
    token_count INTEGER,
    model VARCHAR DEFAULT 'claude-sonnet-4-6'
);

CREATE TABLE IF NOT EXISTS raw.ai_reading_themes (
    theme_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    theme_date DATE NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    theme_content TEXT NOT NULL,
    token_count INTEGER,
    model VARCHAR DEFAULT 'claude-sonnet-4-6'
);

CREATE TABLE IF NOT EXISTS raw.ai_music_narratives (
    narrative_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    narrative_date DATE NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    narrative_content TEXT NOT NULL,
    token_count INTEGER,
    model VARCHAR DEFAULT 'claude-sonnet-4-6'
);

CREATE INDEX IF NOT EXISTS ix_ai_cfb_narratives_game_id ON raw.ai_cfb_narratives(game_id);
CREATE INDEX IF NOT EXISTS ix_ai_life_briefs_date ON raw.ai_life_briefs(brief_date);
CREATE INDEX IF NOT EXISTS ix_ai_habit_insights_date ON raw.ai_habit_insights(insight_date);
CREATE INDEX IF NOT EXISTS ix_ai_reading_themes_date ON raw.ai_reading_themes(theme_date);
CREATE INDEX IF NOT EXISTS ix_ai_music_narratives_date ON raw.ai_music_narratives(narrative_date);
