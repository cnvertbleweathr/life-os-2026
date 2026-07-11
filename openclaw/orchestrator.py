import logging
from datetime import datetime
from openclaw.analyzers import cfb_narratives, morning_brief, weekly_recap
from openclaw.audit import log_openclaw_execution

logger = logging.getLogger(__name__)

def run_openclaw_tier1():
    logger.info("OpenClaw Tier 1 starting...")
    
    try:
        logger.info("  CFB Narratives...")
        result = cfb_narratives.run()
        log_openclaw_execution("cfb_narratives", "generate_text", ["main.mart_cfbd_game_context"], ["raw.ai_cfb_narratives"], result.get("tokens_input", 0), result.get("tokens_output", 0), result.get("cost_usd", 0), "success")
        logger.info(f"    OK CFB: {result['games_processed']} games")
    except Exception as e:
        logger.error(f"    FAIL CFB: {str(e)}")
        log_openclaw_execution("cfb_narratives", "generate_text", [], [], 0, 0, 0, "error", str(e))
    
    try:
        logger.info("  Morning Brief...")
        result = morning_brief.run()
        log_openclaw_execution("morning_brief", "generate_text", ["main.mart_habit_performance"], ["raw.ai_life_briefs"], result.get("tokens_input", 0), result.get("tokens_output", 0), result.get("cost_usd", 0), "success")
        logger.info(f"    OK Brief: {result.get('length_words', 0)} words")
    except Exception as e:
        logger.error(f"    FAIL Brief: {str(e)}")
        log_openclaw_execution("morning_brief", "generate_text", [], [], 0, 0, 0, "error", str(e))
    
    if datetime.now().weekday() == 6:
        try:
            logger.info("  Weekly Recap...")
            result = weekly_recap.run()
            log_openclaw_execution("weekly_recap", "generate_text", ["main.mart_habit_performance"], ["raw.ai_life_briefs"], result.get("tokens_input", 0), result.get("tokens_output", 0), result.get("cost_usd", 0), "success")
            logger.info(f"    OK Recap: {result.get('length_words', 0)} words")
        except Exception as e:
            logger.error(f"    FAIL Recap: {str(e)}")
            log_openclaw_execution("weekly_recap", "generate_text", [], [], 0, 0, 0, "error", str(e))
    
    logger.info("OpenClaw Tier 1 complete")
