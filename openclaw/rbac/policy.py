# openclaw/rbac/policy.py

from enum import Enum
from dataclasses import dataclass

class Capability(Enum):
    """What OpenClaw is allowed to do."""
    ANALYZE_DATA = "analyze_data"
    GENERATE_TEXT = "generate_text"

class ReadableTable(Enum):
    """Tables OpenClaw can SELECT from."""
    MART_CFBD_GAME_CONTEXT = "main.mart_cfbd_game_context"
    MART_CFBD_EXTENDED_EDGES = "main.mart_cfbd_extended_edges"
    MART_CFBD_LINE_ACCURACY = "main.mart_cfbd_line_accuracy"
    MART_HABIT_PERFORMANCE = "main.mart_habit_performance"
    MART_HABIT_STREAKS = "main.mart_habit_streaks"
    MART_GOAL_PROGRESS = "main.mart_goal_progress"
    MART_GOAL_INVENTORY = "main.mart_goal_inventory"
    CFBD_TEAM_PROFILES = "cfbd.team_profiles"
    RAW_GOALS = "raw.raw_goals"
    RAW_GOAL_PROGRESS = "raw.raw_goal_progress"
    HARDCOVER_BOOKS_READ = "hardcover.books_read"
    STRAVA_RUNNING_SUMMARY = "strava.running_summary"

class WritableTable(Enum):
    """Tables OpenClaw can INSERT into."""
    AI_CFB_NARRATIVES = "raw.ai_cfb_narratives"
    AI_LIFE_BRIEFS = "raw.ai_life_briefs"
    AI_HABIT_INSIGHTS = "raw.ai_habit_insights"
    AI_READING_THEMES = "raw.ai_reading_themes"
    AI_MUSIC_NARRATIVES = "raw.ai_music_narratives"

@dataclass
class OpenClawPolicy:
    """Zero-trust RBAC policy."""
    
    readable_tables: list[ReadableTable]
    writable_tables: list[WritableTable]
    capabilities: list[Capability]
    
    def __init__(self):
        self.readable_tables = list(ReadableTable)
        self.writable_tables = list(WritableTable)
        self.capabilities = [Capability.ANALYZE_DATA, Capability.GENERATE_TEXT]
    
    def can_read(self, table: str) -> bool:
        return any(t.value == table for t in self.readable_tables)
    
    def can_write(self, table: str) -> bool:
        return any(t.value == table for t in self.writable_tables)
    
    def has_capability(self, cap: str) -> bool:
        return any(c.value == cap for c in self.capabilities)

OPENCLAW_POLICY = OpenClawPolicy()
