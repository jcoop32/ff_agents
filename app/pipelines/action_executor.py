"""
ActionExecutor: Approval Gate workflow and ESPN Fantasy API write execution.
Enables autonomous agents to draft concrete roster transactions
(waiver claims, lineup swaps, trades, IR moves) and execute them upon user approval.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.pending_action import PendingAction
from app.pipelines.notification_dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)

ESPN_TRANSACTION_URL = "https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}/transactions"
ESPN_WRITES_URL = "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}/transactions"


class ActionExecutor:
    """Manages approval lifecycle and execution of roster actions on ESPN."""

    @classmethod
    async def list_actions(
        cls, status: Optional[str] = "PENDING", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Lists actions from the database filtered by status."""
        async with AsyncSessionLocal() as session:
            stmt = select(PendingAction)
            if status:
                stmt = stmt.where(PendingAction.status == status)
            stmt = stmt.order_by(PendingAction.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            actions = result.scalars().all()
            return [a.to_dict() for a in actions]

    @classmethod
    async def get_action(cls, action_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single pending action by ID."""
        async with AsyncSessionLocal() as session:
            stmt = select(PendingAction).where(PendingAction.id == action_id)
            result = await session.execute(stmt)
            action = result.scalar_one_or_none()
            return action.to_dict() if action else None

    @classmethod
    async def approve_and_execute(cls, action_id: int) -> Dict[str, Any]:
        """
        Approves a pending action and immediately executes it against ESPN.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(PendingAction).where(PendingAction.id == action_id)
            result = await session.execute(stmt)
            action = result.scalar_one_or_none()

            if not action:
                raise ValueError(f"Pending action {action_id} not found.")

            if action.status != "PENDING":
                raise ValueError(f"Action {action_id} is already in state: {action.status}")

            action.status = "APPROVED"
            await session.commit()
            await session.refresh(action)

            # Execute transaction
            exec_result = await cls._execute_espn_transaction(action)
            action.executed_at = datetime.now(timezone.utc)
            action.execution_result = exec_result

            if exec_result.get("success"):
                # A "simulated" execution never touched ESPN: stamp it honestly
                # so the audit trail distinguishes simulation from reality.
                action.status = "SIMULATED" if exec_result.get("simulated") else "EXECUTED"
            else:
                action.status = "FAILED"

            await session.commit()
            await session.refresh(action)
            updated_dict = action.to_dict()

        # Dispatch confirmation briefing
        status_emoji = {"EXECUTED": "✅", "SIMULATED": "🔷"}.get(updated_dict["status"], "❌")
        await NotificationDispatcher.dispatch_briefing(
            briefing_type="ACTION_RESULT",
            urgency="HIGH" if updated_dict["status"] in ("EXECUTED", "SIMULATED") else "CRITICAL",
            title=f"{status_emoji} Action {updated_dict['status']}: {updated_dict['title']}",
            content=(
                f"**Action Type**: {updated_dict['action_type']}\n\n"
                f"**Result**: {exec_result.get('message', 'Completed')}\n\n"
                f"**Details**: {json.dumps(exec_result.get('details', {}), indent=2)}"
            ),
            structured_data=updated_dict,
            source_agent="GeneralManager",
        )

        return updated_dict

    @classmethod
    async def reject_action(cls, action_id: int, reason: str = "Rejected by user") -> Dict[str, Any]:
        """Rejects a pending action."""
        async with AsyncSessionLocal() as session:
            stmt = select(PendingAction).where(PendingAction.id == action_id)
            result = await session.execute(stmt)
            action = result.scalar_one_or_none()

            if not action:
                raise ValueError(f"Pending action {action_id} not found.")

            action.status = "REJECTED"
            action.execution_result = {"reason": reason, "rejected_at": datetime.now(timezone.utc).isoformat()}
            await session.commit()
            await session.refresh(action)
            action_dict = action.to_dict()

        # Dispatch rejection notification
        await NotificationDispatcher.dispatch_briefing(
            briefing_type="ACTION_REJECTED",
            urgency="LOW",
            title=f"🚫 Action Cancelled: {action_dict['title']}",
            content=f"The proposed move has been cancelled. Reason: {reason}",
            structured_data=action_dict,
            source_agent="GeneralManager",
        )

        return action_dict

    @classmethod
    async def expire_stale_actions(cls) -> int:
        """Expires all PENDING actions that have passed expires_at."""
        now = datetime.now(timezone.utc)
        expired_count = 0
        async with AsyncSessionLocal() as session:
            stmt = select(PendingAction).where(
                PendingAction.status == "PENDING",
                PendingAction.expires_at < now,
            )
            result = await session.execute(stmt)
            stale_actions = result.scalars().all()

            for a in stale_actions:
                a.status = "EXPIRED"
                a.execution_result = {"reason": "Expired without user approval"}
                expired_count += 1

            if expired_count > 0:
                await session.commit()
                logger.info("ActionExecutor: Expired %d stale pending actions.", expired_count)

        return expired_count

    @classmethod
    async def _execute_espn_transaction(cls, action: PendingAction) -> Dict[str, Any]:
        """
        Submits formatted transaction to ESPN Fantasy API.
        Handles WAIVER_CLAIM, FREE_AGENT_ADD, LINEUP_SWAP, and IR_STASH.
        """
        payload = action.payload or {}
        action_type = action.action_type

        # Verify ESPN cookies
        if not settings.ESPN_S2 or not settings.ESPN_SWID:
            logger.warning("ESPN_S2 or ESPN_SWID cookies are missing. Simulating execution.")
            return {
                "success": True,
                "simulated": True,
                "message": "Action simulated successfully (ESPN cookies not provided in .env)",
                "details": payload,
            }

        headers = {
            "Cookie": f"espn_s2={settings.ESPN_S2}; SWID={settings.ESPN_SWID}",
            "Content-Type": "application/json",
            "X-Fantasy-Source": "ffl",
            "X-Fantasy-Platform": "kona-web",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

        # Format ESPN request body based on transaction type
        espn_body = {}
        target_url = ESPN_WRITES_URL.format(year=settings.ESPN_YEAR, league_id=settings.ESPN_LEAGUE_ID)

        try:
            if action_type in ["WAIVER_CLAIM", "FREE_AGENT_ADD"]:
                # Items: ADD and optionally DROP
                items = []
                add_id = payload.get("add_player_id")
                drop_id = payload.get("drop_player_id")
                if add_id:
                    items.append({
                        "action": "ADD",
                        "playerId": int(add_id),
                        "type": "LINEUP",
                        "toTeamId": settings.ESPN_TEAM_ID,
                    })
                if drop_id:
                    items.append({
                        "action": "DROP",
                        "playerId": int(drop_id),
                        "type": "LINEUP",
                        "fromTeamId": settings.ESPN_TEAM_ID,
                    })

                espn_body = {
                    "executionType": "PROCESS",
                    "type": "WAIVER" if action_type == "WAIVER_CLAIM" else "FREEAGENT",
                    "items": items,
                    "bidAmount": payload.get("bid_amount", 0),
                }

            elif action_type == "LINEUP_SWAP":
                # Swap bench with starter
                bench_id = payload.get("bench_player_id")
                start_id = payload.get("start_player_id")
                slot_id = payload.get("slot_id", 0)

                items = [
                    {
                        "action": "LINEUP",
                        "playerId": int(bench_id),
                        "type": "LINEUP",
                        "toSlotId": slot_id,
                        "fromSlotId": 20, # Bench
                    },
                    {
                        "action": "LINEUP",
                        "playerId": int(start_id),
                        "type": "LINEUP",
                        "toSlotId": 20, # Bench
                        "fromSlotId": slot_id,
                    },
                ]
                espn_body = {
                    "executionType": "PROCESS",
                    "type": "ROSTER",
                    "items": items,
                }

            elif action_type == "IR_STASH":
                player_id = payload.get("player_id")
                espn_body = {
                    "executionType": "PROCESS",
                    "type": "ROSTER",
                    "items": [
                        {
                            "action": "LINEUP",
                            "playerId": int(player_id),
                            "type": "LINEUP",
                            "toSlotId": 21, # IR slot
                            "fromSlotId": 20, # Bench
                        }
                    ]
                }
            elif action_type == "TRADE_PROPOSAL":
                rec_names = ", ".join(payload.get("receive_player_names", []))
                send_names = ", ".join(payload.get("send_player_names", []))
                opp_name = payload.get("target_team_name", "rival manager")
                return {
                    "success": True,
                    "simulated": False,
                    "message": f"Trade offer ({send_names} for {rec_names}) approved! Ready to submit on ESPN or DM to {opp_name}.",
                    "details": payload,
                }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(target_url, json=espn_body, headers=headers)
                if resp.status_code in [200, 201, 204]:
                    return {
                        "success": True,
                        "status_code": resp.status_code,
                        "message": "Executed successfully on ESPN.",
                        "details": resp.json() if resp.text else {},
                    }
                else:
                    # Try fallback to standard ESPN V3 URL
                    fallback_url = ESPN_TRANSACTION_URL.format(year=settings.ESPN_YEAR, league_id=settings.ESPN_LEAGUE_ID)
                    resp2 = await client.post(fallback_url, json=espn_body, headers=headers)
                    if resp2.status_code in [200, 201, 204]:
                        return {
                            "success": True,
                            "status_code": resp2.status_code,
                            "message": "Executed successfully on ESPN (via fallback).",
                            "details": resp2.json() if resp2.text else {},
                        }
                    return {
                        "success": False,
                        "status_code": resp.status_code,
                        "message": f"ESPN rejected transaction with HTTP {resp.status_code}",
                        "details": resp.text[:500],
                    }

        except Exception as e:
            logger.error("Error executing ESPN transaction: %s", str(e))
            return {
                "success": False,
                "message": f"Exception during ESPN write: {str(e)}",
                "details": {"error": str(e)},
            }
