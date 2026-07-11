import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_MAX_TOKENS = 1000
OPENCLAW_MAX_MONTHLY_BUDGET = 5.00
DUCKDB_PATH = "/Users/kg/life-os-2026/data/warehouse/ons.duckdb"
