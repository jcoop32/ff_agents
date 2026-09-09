"""
Discord Bot Interface for Gridiron AI.
Supports slash commands, real-time responses, proactive league notifications,
and automatic waiver target tracking from conversations.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
import discord
from discord import app_commands
from discord.ext import commands
from app.core.config import settings
from app.core.redis_client import get_redis, init_redis_pool
from app.core.rate_limiter import RateLimiter
from app.agents.supervisor import ask_general_manager
from app.bot.formatters import format_gm_response, format_transaction_alert, format_budget_embed
from app.tools.league_activity_tools import get_recent_transactions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def is_owner_id(user_id: int) -> bool:
    """True only for the configured bot owner."""
    return bool(settings.DISCORD_USER_ID) and str(user_id) == str(settings.DISCORD_USER_ID)


async def deny_non_owner_interaction(interaction: discord.Interaction) -> bool:
    """
    Replies ephemerally to non-owner interactions.
    Returns True when the caller should abort (denied).
    """
    if is_owner_id(interaction.user.id):
        return False
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                "\u26d4 This bot only takes orders from its owner.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "\u26d4 This bot only takes orders from its owner.", ephemeral=True
            )
    except Exception:
        pass
    return True



class ActionApprovalView(discord.ui.View):
    """Interactive Discord UI View with Approve and Reject action buttons."""
    def __init__(self, action_id: int):
        super().__init__(timeout=86400)
        self.action_id = action_id

    @discord.ui.button(label="Approve & Execute", style=discord.ButtonStyle.green, emoji="✅")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await deny_non_owner_interaction(interaction):
            return
        await interaction.response.defer()
        from app.pipelines.action_executor import ActionExecutor
        try:
            res = await ActionExecutor.approve_and_execute(self.action_id)
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(view=self)
            msg = res.get("execution_result", {}).get("message", "Completed")
            await interaction.followup.send(
                f"✅ **Action #{self.action_id} Approved & Executed!**\n"
                f"Status: `{res.get('status')}` • {msg}"
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Failed to execute action #{self.action_id}: {str(e)}")

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await deny_non_owner_interaction(interaction):
            return
        await interaction.response.defer()
        from app.pipelines.action_executor import ActionExecutor
        try:
            res = await ActionExecutor.reject_action(
                self.action_id,
                reason=f"Rejected by {interaction.user.name} via Discord",
            )
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(view=self)
            await interaction.followup.send(f"❌ **Action #{self.action_id} Rejected.**")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error rejecting action: {str(e)}")


async def send_dm_to_user(embed: discord.Embed, view: Optional[discord.ui.View] = None) -> bool:
    """Dispatches a DM to the configured primary user without requiring user initiation."""
    if not settings.DISCORD_USER_ID:
        return False
    try:
        user = await bot.fetch_user(int(settings.DISCORD_USER_ID))
        if user:
            kwargs = {"embed": embed}
            if view is not None:
                kwargs["view"] = view
            await user.send(**kwargs)
            logger.info("Successfully dispatched proactive DM to user %s", settings.DISCORD_USER_ID)
            return True
    except discord.errors.Forbidden:
        logger.warning(
            "Cannot DM user %s: No mutual guild or DMs closed. Ensure bot is in your server.",
            settings.DISCORD_USER_ID,
        )
    except Exception as e:
        logger.error("Failed to dispatch DM to user %s: %s", settings.DISCORD_USER_ID, str(e))
    return False


async def send_channel_alert(
    embed: discord.Embed,
    view: Optional[discord.ui.View] = None,
    mention: bool = False,
) -> bool:
    """Dispatches an embed to the configured server alert/general channel."""
    target_ch = settings.DISCORD_ALERTS_CHANNEL_ID or settings.DISCORD_CHANNEL_ID
    if not target_ch:
        return False
    try:
        ch = bot.get_channel(int(target_ch))
        if not ch:
            ch = await bot.fetch_channel(int(target_ch))
        if ch:
            content = f"<@{settings.DISCORD_USER_ID}>" if mention and settings.DISCORD_USER_ID else None
            kwargs = {"embed": embed}
            if content:
                kwargs["content"] = content
            if view is not None:
                kwargs["view"] = view
            await ch.send(**kwargs)
            logger.info("Successfully posted proactive alert to channel %s", target_ch)
            return True
    except Exception as e:
        logger.error("Failed to post to channel %s: %s", target_ch, str(e))
    return False


@bot.event
async def on_ready():
    logger.info("Gridiron AI Discord bot logged in as %s (ID: %s)", bot.user.name, bot.user.id)
    await init_redis_pool()

    # 1. Sync commands globally
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d global slash commands.", len(synced))
    except Exception as e:
        logger.error("Failed to sync global slash commands: %s", str(e))

    # 2. Sync commands to all joined guilds immediately (bypasses Discord 1-hour global cache)
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            logger.info("Synced commands to server: %s (ID: %s)", guild.name, guild.id)
        except Exception as e:
            logger.warning("Could not sync to guild %s: %s", guild.name, str(e))

    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands"
    if len(bot.guilds) == 0:
        logger.warning(
            "⚠️ Bot is not currently in any Discord servers! "
            "To use slash commands in your server and receive DMs, add the bot via:\n%s",
            invite_url
        )
    else:
        logger.info("Bot is active in %d servers: %s", len(bot.guilds), [g.name for g in bot.guilds])

    # 3. Check proactive DM readiness and dispatch handshake if not sent recently
    if settings.DISCORD_USER_ID and len(bot.guilds) > 0:
        try:
            r = await get_redis()
            boot_key = f"discord:boot_handshake:{bot.user.id}"
            already_sent = await r.get(boot_key)
            if not already_sent:
                embed = discord.Embed(
                    title="🏈 Jarvis 2.0 Proactive Sentinel Online",
                    description=(
                        f"Autonomous direct link established across server **{bot.guilds[0].name}**.\n\n"
                        "I am configured to reach out to you proactively with:\n"
                        "• 🚨 **Injury Alerts & Sunday Lineup Locks**\n"
                        "• ⚡ **Roster Actions** (with one-tap Approve/Reject buttons)\n"
                        "• 🎯 **Priority Waiver Wire Scouting**\n"
                        "• ☀️ **Daily Intelligence Briefings**\n\n"
                        "*No user prompt needed—I will alert you as soon as breaking news hits.*"
                    ),
                    color=0x10B981,
                )
                embed.set_footer(text="Gridiron AI Autonomous Sentinel • Active")
                sent = await send_dm_to_user(embed=embed)
                if sent:
                    await r.set(boot_key, "1", ex=86400)
                    logger.info("Dispatched startup proactive sentinel handshake DM to user %s", settings.DISCORD_USER_ID)
        except Exception as e:
            logger.warning("Notice on boot handshake DM: %s", str(e))

    # Launch proactive notification listener loop
    bot.loop.create_task(proactive_alert_listener())


@bot.event
async def on_guild_join(guild: discord.Guild):
    """When the bot is added to a server, sync commands immediately."""
    logger.info("Joined server: %s (ID: %s). Syncing slash commands...", guild.name, guild.id)
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        logger.info("Successfully synced commands to newly joined server: %s", guild.name)
    except Exception as e:
        logger.error("Failed to sync commands to %s: %s", guild.name, str(e))


@bot.event
async def on_message(message: discord.Message):
    """
    Handles direct messages, user mentions, and prefix commands (!ask, !lineup, !trade, etc.).
    Mirrors the beloved Jarvis direct conversation experience.
    """
    if message.author == bot.user:
        return

    if not is_owner_id(message.author.id):
        await message.channel.send("\u26d4 This bot only takes orders from its owner.")
        return

    content = message.content.strip()
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions

    # 1. Prefix Commands
    if content.startswith("!"):
        parts = content[1:].strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ["ask", "gm", "ai"]:
            query = arg or "Give me a strategic health and waiver check on our fantasy roster."
            async with message.channel.typing():
                try:
                    res = await ask_general_manager(query)
                    embed = format_gm_response(query, res)
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"⚠️ General Manager error: {str(e)}")
            return

        elif cmd == "lineup":
            week = int(arg) if arg.isdigit() else 1
            prompt = f"Optimize our starting lineup for Week {week} in {settings.LEAGUE_SIZE}-team full PPR (3-WR + 1-FLEX). Compare floor vs ceiling matchups."
            async with message.channel.typing():
                try:
                    res = await ask_general_manager(prompt, active_week=week)
                    embed = format_gm_response(f"Lineup Optimization Week {week}", res)
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"⚠️ Lineup error: {str(e)}")
            return

        elif cmd == "trade":
            if not arg:
                await message.channel.send("Usage: `!trade Giving [Player A], Receiving [Player B]`")
                return
            prompt = f"Evaluate this trade for Team Cooper in {settings.LEAGUE_SIZE}-team PPR (3-WR + FLEX): {arg}."
            async with message.channel.typing():
                try:
                    res = await ask_general_manager(prompt)
                    embed = format_gm_response(f"Trade Evaluation: {arg}", res)
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"⚠️ Trade error: {str(e)}")
            return

        elif cmd in ["briefings", "briefing", "pulse"]:
            from app.core.database import AsyncSessionLocal
            from app.models.agent_briefing import AgentBriefing
            from sqlalchemy import select
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(AgentBriefing).order_by(AgentBriefing.created_at.desc()).limit(5)
                    res = await session.execute(stmt)
                    briefings = res.scalars().all()
                if not briefings:
                    await message.channel.send("No agent briefings recorded yet.")
                    return
                embed = discord.Embed(title="🧠 Latest Proactive Agent Briefings", color=0x3B82F6)
                for b in briefings:
                    embed.add_field(name=f"[{b.urgency}] {b.title}", value=f"{b.content[:250]}...\n*Agent: {b.source_agent}*", inline=False)
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f"⚠️ Error: {str(e)}")
            return

        elif cmd in ["actions", "approval"]:
            from app.pipelines.action_executor import ActionExecutor
            try:
                actions = await ActionExecutor.list_actions(status="PENDING", limit=5)
                if not actions:
                    await message.channel.send("✅ No pending actions awaiting approval.")
                    return
                embed = discord.Embed(title="⚡ Pending Roster Actions Awaiting Approval", color=0xF59E0B)
                for a in actions:
                    embed.add_field(name=f"[{a['action_type']}] {a['title']}", value=f"{a['rationale'][:250]}...\n*Approve or reject on the Command Center*", inline=False)
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f"⚠️ Error: {str(e)}")
            return

        elif cmd in ["testdm", "testalert", "test_alert", "ping"]:
            embed = discord.Embed(
                title="🏈 Gridiron AI Sentinel: Proactive Link Active",
                description=(
                    "✅ **Proactive Direct Message pipeline is operational!**\n\n"
                    "The bot can reach out to you autonomously without you having to initiate.\n\n"
                    "You will receive automatic alerts here for:\n"
                    "• 🚨 Roster injury updates & game-day scratches\n"
                    "• 🎯 High-priority waiver wire claims\n"
                    "• ⚡ Approval requests for autonomous moves (with instant buttons)\n"
                    "• ☀️ Daily morning intelligence briefings"
                ),
                color=0x10B981,
            )
            embed.set_footer(text=f"Jarvis 2.0 • User: {message.author.name} ({message.author.id})")
            dm_ok = await send_dm_to_user(embed=embed)
            ch_ok = await send_channel_alert(embed=embed, mention=True)
            await message.channel.send(
                f"✅ **Proactive Outreach Test Dispatched:**\n• Direct Message: {'✅ Delivered' if dm_ok else '❌ Failed'}\n• Channel Broadcast: {'✅ Sent' if ch_ok else '❌ Failed'}"
            )
            return

        elif cmd in ["help", "commands"]:
            embed = discord.Embed(
                title="🏈 Gridiron AI Discord Interface",
                description="Your Autonomous Fantasy General Manager is ready to assist:",
                color=0x3B82F6
            )
            embed.add_field(name="Direct Chat", value="Just DM Jarvis 2.0 or @mention in any channel with your questions!", inline=False)
            embed.add_field(name="!ask <question>", value="Ask the General Manager any strategy, sit/start, or waiver query", inline=False)
            embed.add_field(name="!lineup [week]", value="Simulate optimal floor vs ceiling starting lineup", inline=False)
            embed.add_field(name="!trade <details>", value="Evaluate player equity and VORP impact", inline=False)
            embed.add_field(name="!briefings", value="View latest proactive scouting & injury alerts", inline=False)
            embed.add_field(name="!actions", value="View pending roster moves requiring your approval", inline=False)
            embed.add_field(name="Slash Commands", value="Type `/` to access rich modal slash commands (`/ask`, `/lineup`, `/trade`, `/track`, etc.)", inline=False)
            await message.channel.send(embed=embed)
            return

    # 2. Direct Messages (DMs) or @Mentions
    if is_dm or is_mention:
        clean_text = content
        if is_mention:
            clean_text = clean_text.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

        if not clean_text:
            clean_text = "Status check on our fantasy football team."

        async with message.channel.typing():
            try:
                res = await ask_general_manager(clean_text)
                embed = format_gm_response(clean_text, res)
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f"⚠️ General Manager error: {str(e)}")
        return

    await bot.process_commands(message)


async def proactive_alert_listener():
    """
    Continuous background worker listening for:
    1. Unnotified transactions (waiver claims, drops, trades)
    2. Autonomous agent briefings (injuries, digests, matchup warnings)
    3. Pending roster actions awaiting human approval (with interactive Discord buttons)
    Dispatches directly to user DMs and the server alerts channel without requiring user initiation.
    """
    await bot.wait_until_ready()
    logger.info("Proactive Discord notification listener active (10s cycle).")

    while not bot.is_closed():
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.transaction import Transaction
            from app.models.agent_briefing import AgentBriefing
            from app.models.pending_action import PendingAction
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                # 1. Process unnotified league transactions
                tx_stmt = select(Transaction).where(Transaction.notified == False).limit(5)
                tx_res = await session.execute(tx_stmt)
                unnotified_txs = tx_res.scalars().all()

                for tx in unnotified_txs:
                    embed = format_transaction_alert(tx.to_dict())
                    if tx.impact_level in ["CRITICAL", "HIGH"]:
                        await send_dm_to_user(embed=embed)
                    await send_channel_alert(embed=embed, mention=(tx.impact_level == "CRITICAL"))
                    tx.notified = True

                # 2. Process unnotified Agent Briefings
                b_stmt = select(AgentBriefing).where(AgentBriefing.notified_discord == False).limit(5)
                b_res = await session.execute(b_stmt)
                unnotified_briefings = b_res.scalars().all()

                for b in unnotified_briefings:
                    color_map = {
                        "CRITICAL": 0xEF4444,
                        "HIGH": 0xF59E0B,
                        "MEDIUM": 0x3B82F6,
                        "LOW": 0x10B981,
                    }
                    embed = discord.Embed(
                        title=b.title,
                        description=b.content[:4000],
                        color=color_map.get(b.urgency, 0x3B82F6),
                    )
                    embed.set_footer(text=f"Agent: {b.source_agent} • Type: {b.briefing_type} • Urgency: {b.urgency}")

                    # Proactive reach out: DM on CRITICAL, HIGH, or morning digest
                    is_dm_worthy = (
                        b.urgency in ["CRITICAL", "HIGH"]
                        or b.briefing_type in ["MORNING_DIGEST", "LINEUP_ALERT", "ACTION_RESULT"]
                    )
                    if is_dm_worthy:
                        await send_dm_to_user(embed=embed)

                    # Post to alerts channel
                    await send_channel_alert(embed=embed, mention=(b.urgency == "CRITICAL"))
                    b.notified_discord = True

                # 3. Process unnotified Pending Actions awaiting human approval
                r = await get_redis()
                act_stmt = (
                    select(PendingAction)
                    .where(PendingAction.status == "PENDING")
                    .order_by(PendingAction.created_at.desc())
                    .limit(5)
                )
                act_res = await session.execute(act_stmt)
                pending_actions = act_res.scalars().all()

                for action in pending_actions:
                    action_key = f"discord:notified_action:{action.id}"
                    already_notified = await r.get(action_key)
                    if already_notified:
                        continue

                    embed = discord.Embed(
                        title=f"⚡ Roster Decision Required: {action.title}",
                        description=(
                            f"**Action**: `{action.action_type}` • **Urgency**: `{action.urgency}` • **Confidence**: `{int(action.confidence_score * 100)}%`\n\n"
                            f"**Description**:\n{action.description}\n\n"
                            f"**Rationale**:\n{action.rationale}\n\n"
                            f"*Tap a button below to execute immediately on ESPN, or reject.*"
                        ),
                        color=0xEF4444 if action.urgency == "CRITICAL" else 0xF59E0B,
                    )
                    embed.set_footer(text=f"Gridiron AI Autonomous Supervisor • Action #{action.id}")

                    # Send interactive view via DM and Channel
                    view_dm = ActionApprovalView(action.id)
                    await send_dm_to_user(embed=embed, view=view_dm)

                    view_ch = ActionApprovalView(action.id)
                    await send_channel_alert(embed=embed, view=view_ch, mention=True)

                    # Mark notified for 7 days
                    await r.set(action_key, "1", ex=604800)

                await session.commit()
        except Exception as e:
            logger.error("Error in proactive alert listener: %s", str(e))

        await asyncio.sleep(10)  # Responsive 10-second polling cycle


# ==========================================
# Slash Commands
# ==========================================

@bot.tree.command(name="ask", description="Ask the General Manager any fantasy football question")
@app_commands.describe(question="Your sit/start, waiver, or strategy question")
async def slash_ask(interaction: discord.Interaction, question: str):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer(thinking=True)

    # Auto-track waiver target if user asks about a pickup
    if any(k in question.lower() for k in ["pick up", "add", "waiver", "claim", "stash"]):
        words = question.split()
        # Track words as possible player mention
        r = await get_redis()
        await r.sadd("user:waiver_targets", question)

    try:
        response = await ask_general_manager(question)
        embed = format_gm_response(question, response)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error from General Manager: {str(e)}")


@bot.tree.command(name="lineup", description="Evaluate optimal sit/start lineup decisions for this week")
@app_commands.describe(week="Fantasy week to optimize")
async def slash_lineup(interaction: discord.Interaction, week: int = 1):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer(thinking=True)
    prompt = f"Optimize our starting lineup for Week {week} in 12-team full PPR (3-WR + 1-FLEX). Compare floor vs ceiling matchups."
    response = await ask_general_manager(prompt, active_week=week)
    embed = format_gm_response(f"Lineup Optimization Week {week}", response)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="trade", description="Analyze a proposed trade offer for value equity and lineup delta")
@app_commands.describe(players_sent="Players you are giving up", players_received="Players you are getting")
async def slash_trade(interaction: discord.Interaction, players_sent: str, players_received: str):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer(thinking=True)
    prompt = f"Evaluate this trade for Team Cooper in 12-team PPR (3-WR + FLEX): Giving [{players_sent}], Receiving [{players_received}]."
    response = await ask_general_manager(prompt)
    embed = format_gm_response(f"Trade: Giving {players_sent} for {players_received}", response)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="draft", description="Get live draft recommendation or tier-cliff analysis")
@app_commands.describe(position="Position to evaluate or target")
async def slash_draft(interaction: discord.Interaction, position: str = "ALL"):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer(thinking=True)
    prompt = f"Provide live draft room recommendation at position '{position}'. Identify active tier cliffs and VORP values."
    response = await ask_general_manager(prompt)
    embed = format_gm_response(f"Draft Strategy [{position}]", response)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="waiver", description="Add a player to your target watchlist or evaluate waiver pool")
@app_commands.describe(target_player="Player name to add to priority watchlist")
async def slash_waiver(interaction: discord.Interaction, target_player: str):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer()
    r = await get_redis()
    await r.sadd("user:waiver_targets", target_player.strip())
    await interaction.followup.send(
        f"🎯 **Watchlist Updated**: '{target_player}' is now on your priority target list. "
        "The system will alert you immediately if any other league manager attempts to claim this player."
    )


@bot.tree.command(name="budget", description="Check remaining free-tier LLM API usage for today")
async def slash_budget(interaction: discord.Interaction):
    if await deny_non_owner_interaction(interaction):
        return
    status = await RateLimiter.get_budget_status()
    embed = format_budget_embed(status)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="activity", description="View recent transactions and impact in WA minus Josh")
async def slash_activity(interaction: discord.Interaction):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer()
    txs = await get_recent_transactions(hours=48)
    if not txs:
        await interaction.followup.send("No league transactions logged in the past 48 hours.")
        return

    lines = []
    for t in txs[:8]:
        added = ", ".join([p.get("name", "") for p in t.get("players_added", [])])
        dropped = ", ".join([p.get("name", "") for p in t.get("players_dropped", [])])
        lines.append(f"• **[{t.get('impact_level', 'LOW')}]** {t.get('team_name')}: +{added} / -{dropped}")

    embed = discord.Embed(
        title="📋 Recent League Transactions (Past 48h)",
        description="\n".join(lines),
        color=0x3B82F6
    )
@bot.tree.command(name="track", description="Spawn an autonomous background surveillance job for an NFL player")
@app_commands.describe(player_name="NFL player to monitor", frequency_minutes="Polling frequency in minutes (e.g. 30, 60)")
async def slash_track(interaction: discord.Interaction, player_name: str, frequency_minutes: int = 60):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer()
    from app.pipelines.scheduler_api import SchedulerAPI
    try:
        job = await SchedulerAPI.spawn_tracking_job(
            player_name=player_name,
            frequency_minutes=frequency_minutes,
            duration_hours=48,
            reason="Spawned via Discord /track command",
            source="discord",
        )
        embed = discord.Embed(
            title=f"🎯 Tracking Job Spawned: {player_name}",
            description=(
                f"Autonomous background surveillance is now active for **{player_name}**.\n\n"
                f"• **Frequency**: Every {frequency_minutes} minutes\n"
                f"• **Focus Areas**: Injury updates, practice participation (DNP/LP), depth chart changes\n"
                f"• **Adaptive Scaling**: Frequency will automatically escalate to every 15m if injury worsens\n"
                f"• **Job ID**: `{job['job_id']}`\n\n"
                f"Manage and cancel this job anytime in the **Tracking** dashboard."
            ),
            color=0x10B981,
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to spawn tracking job: {str(e)}")


@bot.tree.command(name="briefings", description="View the latest autonomous intelligence briefings from the agents")
async def slash_briefings(interaction: discord.Interaction):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer()
    from app.core.database import AsyncSessionLocal
    from app.models.agent_briefing import AgentBriefing
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(AgentBriefing).order_by(AgentBriefing.created_at.desc()).limit(5)
            res = await session.execute(stmt)
            briefings = res.scalars().all()

        if not briefings:
            await interaction.followup.send("No agent briefings recorded yet.")
            return

        embed = discord.Embed(
            title="🧠 Latest Proactive Agent Briefings",
            color=0x3B82F6,
        )
        for b in briefings:
            embed.add_field(
                name=f"[{b.urgency}] {b.title}",
                value=f"{b.content[:200]}...\n*Agent: {b.source_agent}*",
                inline=False,
            )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error fetching briefings: {str(e)}")


@bot.tree.command(name="actions", description="View pending roster actions awaiting your approval")
async def slash_actions(interaction: discord.Interaction):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer()
    from app.pipelines.action_executor import ActionExecutor
    try:
        actions = await ActionExecutor.list_actions(status="PENDING", limit=5)
        if not actions:
            await interaction.followup.send("✅ No pending actions awaiting approval.")
            return

        embed = discord.Embed(
            title="⚡ Pending Roster Actions Awaiting Approval",
            description="Autonomous moves formulated by agents requiring human approval:",
            color=0xF59E0B,
        )
        for a in actions:
            embed.add_field(
                name=f"[{a['action_type']}] {a['title']} (Confidence: {int(a['confidence_score'] * 100)}%)",
                value=f"{a['rationale'][:250]}...\n*Approve or reject on the Command Center*",
                inline=False,
            )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error fetching pending actions: {str(e)}")


@bot.tree.command(name="test_alert", description="Test Jarvis 2.0 proactive outreach directly to your DMs and channel")
async def slash_test_alert(interaction: discord.Interaction):
    if await deny_non_owner_interaction(interaction):
        return
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(
        title="🏈 Proactive Outreach Pipeline Test",
        description=(
            "✅ **Autonomous Direct Message outreach verified!**\n\n"
            "Jarvis 2.0 can reach out to you directly and proactively without requiring you to message first.\n\n"
            "Active triggers:\n"
            "• 🚨 High-urgency injury alerts & inactive notices\n"
            "• ⚡ Proposed roster moves requiring approval\n"
            "• 🎯 High-priority waiver claims\n"
            "• ☀️ Daily morning intelligence briefings"
        ),
        color=0x10B981,
    )
    embed.set_footer(text=f"Gridiron AI Autonomous Sentinel • User {settings.DISCORD_USER_ID}")
    dm_sent = await send_dm_to_user(embed=embed)
    channel_sent = await send_channel_alert(embed=embed, mention=True)
    await interaction.followup.send(
        f"**Proactive Outreach Test:**\n• Direct Message: {'✅ Successfully Delivered' if dm_sent else '❌ Failed'}\n• Channel Broadcast: {'✅ Successfully Sent' if channel_sent else '❌ Failed'}",
        ephemeral=True,
    )


def main():
    if not settings.DISCORD_BOT_TOKEN:
        logger.warning("DISCORD_BOT_TOKEN not configured. Discord bot idle (waiting for token).")
        import time
        while True:
            time.sleep(3600)
    bot.run(settings.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
