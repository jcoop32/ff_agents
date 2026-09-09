"""
Direct execution tests for the 9 Proactive Autonomous Jobs.
Verifies that each autonomous job coroutine runs without raising unhandled exceptions.
"""

import pytest
from unittest.mock import patch, AsyncMock
from app.pipelines.proactive_jobs import (
    job_morning_digest,
    job_waiver_scout,
    job_trade_finder,
    job_lineup_lock,
    job_practice_monitor,
    job_news_poller,
    job_transaction_poller,
    job_power_rankings,
    job_season_strategy,
)


@pytest.mark.asyncio
async def test_all_proactive_jobs_execute_cleanly():
    """Smoke test ensuring each job completes without crashing."""
    # 1. Morning digest
    await job_morning_digest()

    # 2. Waiver scout
    await job_waiver_scout()

    # 3. Trade finder
    await job_trade_finder()

    # 4. Lineup lock
    await job_lineup_lock()

    # 5. Practice monitor (mock external research to avoid hitting web rate limits during test)
    with patch("app.tools.web_research.WebResearchService.research_player", new_callable=AsyncMock) as mock_res:
        mock_res.return_value = {"summary": "Limited participation due to ankle maintenance."}
        await job_practice_monitor()

    # 6. News poller
    await job_news_poller()

    # 7. Transaction poller
    await job_transaction_poller()

    # 8. Power rankings
    await job_power_rankings()

    # 9. Season strategy
    await job_season_strategy()
