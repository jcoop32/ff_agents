"""
Application configuration using Pydantic Settings.
Loads from environment variables and .env file.
"""

from typing import List
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Project Info
    PROJECT_NAME: str = "Gridiron AI"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # LLM API Keys
    GOOGLE_API_KEY: str = Field(default="", description="Google AI Studio API key")
    GROQ_API_KEY: str = Field(default="", description="Groq Cloud API key")

    # ESPN Fantasy Configuration
    ESPN_LEAGUE_ID: int = Field(default=0, description="ESPN League ID")
    ESPN_TEAM_ID: int = Field(default=1, description="Fantasy Team ID")
    ESPN_S2: str = Field(default="", description="ESPN S2 Cookie for private league")
    ESPN_SWID: str = Field(default="", description="ESPN SWID Cookie for private league")
    ESPN_YEAR: int = Field(default=2026, description="Fantasy Season Year")

    # Infrastructure Connection URLs
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Async Redis URL")
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://gridiron:gridiron@localhost:5432/gridiron",
        description="SQLAlchemy asyncpg PostgreSQL connection string"
    )

    # Discord Integration
    DISCORD_BOT_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices("DISCORD_BOT_TOKEN", "DISCORD_TOKEN"),
        description="Discord bot token"
    )
    DISCORD_CHANNEL_ID: str = Field(default="", description="Default interaction channel")
    DISCORD_ALERTS_CHANNEL_ID: str = Field(default="", description="#league-alerts channel")
    DISCORD_DIGEST_CHANNEL_ID: str = Field(default="", description="#league-digest channel")
    DISCORD_USER_ID: str = Field(default="", description="Personal Discord user ID for DMs")

    # League Settings ("WA minus Josh")
    SCORING_FORMAT: str = Field(default="ppr", description="Scoring format (ppr, half_ppr, standard)")
    LEAGUE_SIZE: int = Field(default=10, description="Number of teams in league")
    NUM_WR_SLOTS: int = Field(default=3, description="Starting wide receiver slots")
    HAS_FLEX: bool = Field(default=True, description="Whether league has a FLEX slot")
    PASSING_YARDS_PER_POINT: float = Field(default=20.0, description="0.05 per yard = 1 pt per 20 yards")
    IS_SUPERFLEX: bool = Field(default=False, description="Superflex 2QB format")
    IS_TE_PREMIUM: bool = Field(default=False, description="Tight end premium")
    BENCH_SLOTS: int = Field(default=4, description="Number of bench spots")
    IR_SLOTS: int = Field(default=1, description="Number of IR spots")

    # LLM Model Routing
    SUPERVISOR_MODEL: str = Field(default="gemini-3.5-flash", description="General Manager model")
    REPORTING_MODEL: str = Field(default="gemini-3.5-flash", description="Reporting & Intel model")
    FAST_MODEL: str = Field(default="qwen/qwen3.6-27b", description="Fast tool-calling Groq model")
    HEAVY_MODEL: str = Field(default="openai/gpt-oss-120b", description="Deep reasoning Groq model")
    EMBEDDING_MODEL: str = Field(default="models/text-embedding-004", description="Gemini embedding model")

    # Proactive Monitor & Rate Limiter Policies
    MAX_PROACTIVE_LLM_PER_DAY: int = Field(default=25, description="Max proactive agent LLM calls per day")
    LEAGUE_MONITOR_INTERVAL_MINUTES: int = Field(default=10, description="Interval to poll ESPN transactions")
    NEWS_POLL_INTERVAL_MINUTES: int = Field(default=15, description="Interval to poll news RSS feeds")
    LLM_CACHE_TTL_HOURS: int = Field(default=4, description="Default response cache TTL")

    # Autonomous & Proactive Agent Settings
    PROACTIVE_MODE_ENABLED: bool = Field(default=True, description="Enable autonomous agent background execution")
    SCHEDULER_TIMEZONE: str = Field(default="America/Chicago", description="Scheduler timezone (CST)")
    ENABLE_APPROVAL_GATES: bool = Field(default=True, description="Require user approval for roster moves")
    AUTO_EXECUTE_HIGH_CONFIDENCE: bool = Field(default=False, description="Auto-execute actions with >0.95 confidence")
    ACTION_EXPIRY_HOURS: int = Field(default=24, description="Hours before pending actions expire")
    ENABLE_WEB_RESEARCH: bool = Field(default=True, description="Enable Gemini Google Search grounding")
    REDDIT_RESEARCH_ENABLED: bool = Field(default=True, description="Enable r/fantasyfootball sentiment search")

    # Default Autonomous Schedules
    MORNING_DIGEST_CRON: str = Field(default="0 7 * * *", description="Daily 7:00 AM briefing")
    WAIVER_SCOUT_CRON: str = Field(default="0 6,18 * * *", description="6:00 AM and 6:00 PM waiver scan")
    TRADE_FINDER_CRON: str = Field(default="0 11 * * *", description="11:00 AM daily trade exploration")
    PRACTICE_MONITOR_CRON: str = Field(default="0 15,17 * * 3,4,5", description="Wed/Thu/Fri practice injury checks")
    LINEUP_LOCK_CRON: str = Field(default="30 11,12 * * 0", description="Sunday 11:30 AM & 12:45 PM kickoffs")
    POWER_RANKINGS_CRON: str = Field(default="0 9 * * 2", description="Tuesday 9:00 AM post-week power rankings")
    SEASON_STRATEGY_CRON: str = Field(default="0 10 * * 3", description="Wednesday 10:00 AM macro strategy")

    # Networking & Tailscale CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
    ]
    # Allowed Tailscale and internal IP regex/prefixes will be handled dynamically in CORS middleware


settings = Settings()
