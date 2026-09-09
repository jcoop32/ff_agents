"""
Discord rich embed formatters for agent outputs and proactive transaction alerts.
"""

import discord
from typing import Dict, Any


def format_gm_response(user_query: str, agent_response: str) -> discord.Embed:
    """Formats General Manager response into a polished front-office card."""
    embed = discord.Embed(
        title="🏈 General Manager Front Office Verdict",
        description=agent_response,
        color=0x1E3A8A # Deep Navy
    )
    from app.core.config import settings
    embed.add_field(name="User Inquiry", value=user_query[:250], inline=False)
    embed.set_footer(text=f"WA minus Josh ({settings.LEAGUE_SIZE}-Team PPR) • Team Cooper GM")
    return embed


def format_transaction_alert(tx: Dict[str, Any]) -> discord.Embed:
    """Formats a proactive league transaction alert based on its impact level."""
    impact = tx.get("impact_level", "LOW")
    colors = {
        "CRITICAL": 0xDC2626, # Red
        "HIGH": 0xF59E0B,     # Amber
        "MEDIUM": 0x3B82F6,   # Blue
        "LOW": 0x6B7280       # Gray
    }
    color = colors.get(impact, 0x3B82F6)

    embed = discord.Embed(
        title=f"🚨 Proactive League Alert: [{impact}]",
        description=f"**{tx.get('team_name', 'League Team')}** executed a transaction:",
        color=color
    )

    added = ", ".join([p.get("name", "Unknown") for p in tx.get("players_added", [])]) or "None"
    dropped = ", ".join([p.get("name", "Unknown") for p in tx.get("players_dropped", [])]) or "None"

    embed.add_field(name="Type", value=tx.get("type", "ROSTER_MOVE"), inline=True)
    embed.add_field(name="Added", value=added, inline=True)
    embed.add_field(name="Dropped", value=dropped, inline=True)

    analysis = tx.get("analysis_text")
    if analysis:
        embed.add_field(name="GM Tactical Analysis", value=analysis[:1024], inline=False)

    embed.set_footer(text="Automatic Proactive League Monitor • ESPN Sync")
    return embed


def format_budget_embed(budget_status: Dict[str, Any]) -> discord.Embed:
    """Formats real-time API quota usage for Gemini and Groq free tiers."""
    embed = discord.Embed(
        title="📊 Cloud LLM Free-Tier Budget Status",
        description="Tracks RPM, RPD, and TPM quotas to ensure $0.00 monthly cost.",
        color=0x10B981 # Emerald Green
    )

    for provider, data in budget_status.items():
        val = (
            f"**Requests Today:** {data['rpd_used']} / {data['rpd_limit']} ({data['rpd_percent']}%)\n"
            f"**Current RPM:** {data['rpm_used']} / {data['rpm_limit']}\n"
            f"**Current TPM:** {data['tpm_used']} / {data['tpm_limit']}\n"
            f"*Resets midnight {data['reset_timezone']}*"
        )
        embed.add_field(name=f"🤖 {provider.upper()}", value=val, inline=False)

    return embed
