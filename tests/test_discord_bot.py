"""
Unit and integration tests for Gridiron AI Discord bot.
"""

import pytest
import discord
from app.core.config import settings
from app.bot.formatters import format_gm_response, format_transaction_alert, format_budget_embed
from app.bot.discord_bot import bot


def test_discord_configuration():
    """Verifies that the bot configuration attributes exist and are valid string types."""
    assert isinstance(settings.DISCORD_BOT_TOKEN, str)
    assert isinstance(settings.DISCORD_USER_ID, str)


def test_format_gm_response():
    """Verifies GM response embeds are formatted properly with league context."""
    embed = format_gm_response("Start Ja'Marr Chase or Amon-Ra?", "Start Ja'Marr Chase for WR1 ceiling.")
    assert embed.title == "🏈 General Manager Front Office Verdict"
    assert "Ja'Marr Chase" in embed.description
    assert f"{settings.LEAGUE_SIZE}-Team PPR" in embed.footer.text


def test_format_transaction_alert():
    """Verifies transaction alert embeds format critical impact styling."""
    tx = {
        "impact_level": "CRITICAL",
        "team_name": "Team Cooper",
        "type": "WAIVER_CLAIM",
        "players_added": [{"name": "Puka Nacua"}],
        "players_dropped": [{"name": "Allen Lazard"}],
        "analysis_text": "High priority waiver addition."
    }
    embed = format_transaction_alert(tx)
    assert embed.color.value == 0xDC2626
    assert "Team Cooper" in embed.description
    assert any(f.name == "Added" and "Puka Nacua" in f.value for f in embed.fields)


def test_format_budget_embed():
    """Verifies budget embed displays rate limit metrics."""
    budget = {
        "gemini": {
            "rpd_used": 5, "rpd_limit": 1500, "rpd_percent": 0.3,
            "rpm_used": 1, "rpm_limit": 15,
            "tpm_used": 200, "tpm_limit": 1000000,
            "reset_timezone": "UTC"
        }
    }
    embed = format_budget_embed(budget)
    assert "GEMINI" in embed.fields[0].name
    assert "5 / 1500" in embed.fields[0].value


def test_bot_registered_commands():
    """Verifies all required slash commands are declared on the command tree."""
    command_names = [cmd.name for cmd in bot.tree.get_commands()]
    required = ["ask", "lineup", "trade", "draft", "waiver", "budget", "activity", "track", "briefings", "actions", "test_alert"]
    for r in required:
        assert r in command_names, f"Expected slash command '{r}' not found on bot tree"


def test_action_approval_view_initialization():
    """Verifies ActionApprovalView correctly mounts Approve and Reject buttons."""
    from app.bot.discord_bot import ActionApprovalView
    view = ActionApprovalView(action_id=42)
    assert view.action_id == 42
    assert len(view.children) == 2
    button_labels = [c.label for c in view.children]
    assert "Approve & Execute" in button_labels
    assert "Reject" in button_labels
