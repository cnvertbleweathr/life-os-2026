# openclaw/audit.py

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

def log_openclaw_execution(
    analyzer_name: str,
    capability_used: str,
    tables_read: list[str],
    tables_written: list[str],
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
    status: str = "success",
    error_message: Optional[str] = None,
):
    """Log OpenClaw execution to audit file (append-only)."""
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "analyzer_name": analyzer_name,
        "capability_used": capability_used,
        "tables_read": tables_read,
        "tables_written": tables_written,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "cost_usd": cost_usd,
        "policy_enforced": True,
        "status": status,
        "error_message": error_message,
    }
    
    audit_file = "/Users/kg/life-os-2026/data/ai/generations.jsonl"
    with open(audit_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    logger.info(f"✓ Audit logged: {analyzer_name} | {status}")
