import logging
from datetime import datetime
import anthropic
from openclaw.db import db

logger = logging.getLogger(__name__)

def run():
    logger.info("CFB Narratives: Starting...")
    games = db.query(
        """
        SELECT g.id, g.home_team, g.away_team, g.home_points, g.away_points
        FROM main.mart_cfbd_game_context c
        JOIN cfbd.games g ON c.game_id = g.id
        WHERE g.home_points IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM raw.ai_cfb_narratives n WHERE n.game_id = g.id)
        ORDER BY g.start_date DESC
        LIMIT 10
        """,
        table_hint="mart_cfbd_game_context",
    )
    
    if not games:
        logger.info("No completed games without narratives")
        return {"games_processed": 0, "tokens_input": 0, "tokens_output": 0, "cost_usd": 0}
    
    client = anthropic.Anthropic()
    system_prompt = """You are OpenClaw, an analytics AI for the Operating Narcisystem.
Generate a 150-word post-game narrative for a college football game.
Format: Opening (result), Analysis (why), Betting insight (line accuracy)."""
    
    narratives = []
    total_input_tokens = 0
    total_output_tokens = 0
    
    for game in games:
        context = f"Game: {game['home_team']} vs {game['away_team']}\nFinal: {game['home_points']}-{game['away_points']}"
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                system=system_prompt,
                messages=[{"role": "user", "content": f"Generate narrative for this game:\n\n{context}"}],
            )
            narrative_text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            narratives.append({"game_id": game["id"], "narrative": narrative_text, "token_count": output_tokens})
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            logger.info(f"  ✓ {game['home_team']} vs {game['away_team']}")
        except Exception as e:
            logger.error(f"  ✗ Failed for game {game['id']}: {str(e)}")
            continue
    
    if narratives:
        db.insert("raw.ai_cfb_narratives", narratives)
        logger.info(f"✓ Inserted {len(narratives)} CFB narratives")
    
    cached_input_cost = (total_input_tokens * 0.10 * 3 / 1_000_000)
    output_cost = (total_output_tokens * 15 / 1_000_000)
    cost_usd = cached_input_cost + output_cost
    
    return {"games_processed": len(narratives), "tokens_input": total_input_tokens, "tokens_output": total_output_tokens, "cost_usd": round(cost_usd, 6)}
