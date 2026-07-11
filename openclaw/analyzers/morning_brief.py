import logging
from datetime import datetime, timedelta
import anthropic
from openclaw.db import db

logger = logging.getLogger(__name__)

def run():
    logger.info("Morning Brief: Starting...")
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    habits = db.query(f"SELECT habit_name, completed FROM main.mart_habit_performance WHERE habit_date = '{yesterday}'", table_hint="mart_habit_performance")
    goals = db.query("SELECT goal_name, progress_pct FROM main.mart_goal_progress WHERE status = 'active' LIMIT 3", table_hint="mart_goal_progress")
    habit_summary = f"{len([h for h in habits if h.get('completed')])} / {len(habits)} habits" if habits else "No habits"
    goals_summary = " | ".join([f"{g['goal_name']}: {g['progress_pct']:.0f}%" for g in goals[:3]]) if goals else "No goals"
    context = f"Yesterday's Summary:\nHabits: {habit_summary}\nGoals: {goals_summary}"
    client = anthropic.Anthropic()
    system_prompt = "You are OpenClaw, daily briefing AI. Generate a 3-4 sentence morning brief (150 words max)."
    try:
        response = client.messages.create(model="claude-sonnet-4-6", max_tokens=300, system=system_prompt, messages=[{"role": "user", "content": context}])
        brief_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        db.insert("raw.ai_life_briefs", [{"brief_date": yesterday, "brief_type": "daily", "brief_content": brief_text, "token_count": output_tokens}])
        cached_input_cost = (input_tokens * 0.10 * 3 / 1_000_000)
        output_cost = (output_tokens * 15 / 1_000_000)
        cost_usd = cached_input_cost + output_cost
        logger.info(f"✓ Morning brief generated: {len(brief_text.split())} words")
        return {"length_words": len(brief_text.split()), "tokens_input": input_tokens, "tokens_output": output_tokens, "cost_usd": round(cost_usd,)}
    except Exception as e:
        logger.error(f"✗ Morning brief failed: {str(e)}")
        raise
