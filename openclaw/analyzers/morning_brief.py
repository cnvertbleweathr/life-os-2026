import logging
from datetime import datetime, timedelta
import anthropic
from openclaw.db import db

logger = logging.getLogger(__name__)

def run():
    logger.info("Morning Brief: Starting...")
    
    # Just get summary counts - no date filtering
    try:
        habits = db.query(
            "SELECT habits_completed_count FROM main_marts.mart_habit_performance LIMIT 1",
            table_hint="mart_habit_performance",
        )
        habit_summary = f"{habits[0].get('habits_completed_count', 0)} habits completed" if habits else "No habits"
    except:
        habit_summary = "No habit data"
    
    context = f"Yesterday's Summary:\nHabits: {habit_summary}"
    
    client = anthropic.Anthropic()
    system_prompt = "You are OpenClaw, daily briefing AI. Generate a 3-4 sentence morning brief (150 words max)."
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": context}],
        )
        
        brief_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        
        db.insert(
            "raw.ai_life_briefs",
            [
                {
                    "brief_date": datetime.now().date().isoformat(),
                    "brief_type": "daily",
                    "brief_content": brief_text,
                    "token_count": output_tokens,
                }
            ],
        )
        
        logger.info(f"✓ Morning brief generated")
        return {
            "length_words": len(brief_text.split()),
            "tokens_input": input_tokens,
            "tokens_output": output_tokens,
            "cost_usd": 0.001,
        }
    except Exception as e:
        logger.error(f"✗ Morning brief failed: {str(e)}")
        return {"length_words": 0, "tokens_input": 0, "tokens_output": 0, "cost_usd": 0}