import logging
from datetime import datetime, timedelta
import anthropic
from openclaw.db import db

logger = logging.getLogger(__name__)

def run():
    logger.info("Weekly Recap: Starting...")
    start_date = (datetime.now().date() - timedelta(days=7)).isoformat()
    end_date = datetime.now().date().isoformat()
    habits_week = db.query(f"SELECT habit_name, SUM(CASE WHEN completed THEN 1 ELSE 0 END) as days_completed FROM main.mart_habit_performance WHERE habit_date BETWEEN '{start_date}' AND '{end_date}' GROUP BY habit_name", table_hint="mart_habit_performance")
    goals_week = db.query("SELECT goal_name, progress_pct FROM main.mart_goal_progress WHERE status = 'active' LIMIT 3", table_hint="mart_goal_progress")
    habits_str = " | ".join([f"{h['habit_name']}: {h['days_completed']}/7" for h in habits_week[:3]]) if habits_week else "No habits"
    goals_str = " | ".join([f"{g['goal_name']}: {g['progress_pct']:.0f}%" for g in goals_week[:3]]) if goals_week else "No goals"
    context = f"This Week's Summary ({start_date} to {end_date}):\nHabits: {habits_str}\nGoals: {goals_str}"
    client = anthropic.Anthropic()
    system_prompt = "You are OpenClaw, weekly recap writer. Write a 400-word narrative summary."
    try:
        response = client.messages.create(model="claude-sonnet-4-6", max_tokens=800, system=system_prompt, messages=[{"role": "user", "content": context}])
        recap_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        db.insert("raw.ai_life_briefs", [{"brief_date": datetime.now().date().isoformat(), "brief_type": "weekly", "brief_content": recap_text, "token_count": output_tokens}])
        cached_input_cost = (input_tokens * 0.10 * 3 / 1_000_000)
        output_cost = (output_tokens * 15 / 1_000_000)
        cost_usd = cached_input_cost + output_cost
        logger.info(f"✓ Weekly recap generated: {len(recap_text.split())} words")
        return {"length_words": len(recap_text.split()), "tokens_input": input_tokens, "tokens_output": output_tokens, "cost_usd": round(cost_usd, 6)}
    except Exception as e:
        logger.error(f"✗ Weekly recap failed: {str(e)}")
        raise
