"""
Tier 3 Volatile News Pipeline: RSS Polling & Real-Time Ingestion.
Extracts player mentions, classifies injury designations (Q/D/O/IR/LP/FP/DNP),
stores semantic pgvector embeddings, and updates Redis news feeds.
"""

import time
import logging
from typing import Dict, Any, List, Optional
import feedparser
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import RedisRepository, get_redis
from app.models.player import Player
from app.models.stats import NewsItem

logger = logging.getLogger(__name__)

# RSS Feeds for reliable NFL & fantasy breaking news
RSS_FEEDS = [
    {"source": "RotoWire", "url": "https://www.rotowire.com/rss/news.php?sport=NFL"},
    {"source": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news"},
]


class NewsIngestionService:
    """Consumes external feeds, generates embeddings, and indexes volatile news."""

    @classmethod
    async def poll_rss_feeds(cls) -> Dict[str, Any]:
        """Polls configured RSS feeds and ingests new items."""
        total_ingested = 0

        for feed_config in RSS_FEEDS:
            source = feed_config["source"]
            url = feed_config["url"]
            try:
                parsed = feedparser.parse(url)
                for entry in parsed.entries[:10]: # Process top 10 most recent
                    headline = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "") or headline
                    link = getattr(entry, "link", "")

                    if not headline:
                        continue

                    # Ingest item through unified handler
                    ingested = await cls.process_news_item({
                        "source": source,
                        "headline": headline,
                        "text": summary,
                        "url": link
                    })
                    if ingested:
                        total_ingested += 1
            except Exception as e:
                logger.error("Error polling RSS feed %s: %s", source, str(e))

        return {"success": True, "items_ingested": total_ingested}

    @classmethod
    async def process_news_item(cls, payload: Dict[str, Any]) -> bool:
        """
        Parses news content, maps to player, extracts injury status,
        persists to PostgreSQL & Redis, and updates entity tags.
        """
        headline = payload.get("headline", "")
        text = payload.get("text", "")
        source = payload.get("source", "Manual")
        url = payload.get("url")

        content = f"{headline} {text}"
        tag = cls._extract_injury_tag(content)

        async with AsyncSessionLocal() as session:
            # Check duplicate by URL if provided
            if url:
                existing = await session.execute(select(NewsItem).where(NewsItem.url == url))
                if existing.scalar_one_or_none():
                    return False

            # Match player mention
            player_match = await cls._match_player_in_text(content, session)
            player_id = player_match.id if player_match else None
            espn_id = player_match.espn_id if player_match else None
            player_name = player_match.name if player_match else None

            # Generate semantic embedding if Google API key available
            embedding_vector = await cls._generate_embedding(content)

            news_db = NewsItem(
                player_id=player_id,
                espn_id=espn_id,
                player_name=player_name,
                source=source,
                tag=tag,
                headline=headline,
                text=text,
                url=url,
                embedding=embedding_vector
            )
            session.add(news_db)

            # Update player status if official tag found
            if player_match and tag in ("Questionable", "Doubtful", "Out", "IR"):
                player_match.injury_status = tag

            await session.commit()

        # Update Redis real-time indexes
        epoch = time.time()
        news_payload = {
            "source": source,
            "headline": headline,
            "text": text,
            "tag": tag,
            "timestamp": epoch
        }

        if espn_id:
            await RedisRepository.add_player_news(espn_id, epoch, news_payload)
            if tag:
                # Patch player hash in Redis
                r = await get_redis()
                await r.hset(f"player:{espn_id}", "status", tag)

        # Broadcast to stream:raw_news
        await RedisRepository.push_raw_news_stream(news_payload)
        return True

    @staticmethod
    def _extract_injury_tag(text: str) -> Optional[str]:
        t = text.lower()
        if "out" in t or "ruled out" in t:
            return "Out"
        elif "doubtful" in t:
            return "Doubtful"
        elif "questionable" in t or "game-time decision" in t:
            return "Questionable"
        elif "dnp" in t or "did not participate" in t:
            return "DNP"
        elif "limited" in t or "lp" in t:
            return "LP"
        elif "full" in t or "fp" in t:
            return "FP"
        elif "injured reserve" in t or "placed on ir" in t:
            return "IR"
        return None

    @staticmethod
    async def _match_player_in_text(text: str, session) -> Optional[Player]:
        """Fuzzy matches player names against database records."""
        # Simple scan of active players
        stmt = select(Player).limit(100)
        res = await session.execute(stmt)
        players = res.scalars().all()
        for p in players:
            if p.name.lower() in text.lower():
                return p
        return None

    @staticmethod
    async def _generate_embedding(text: str) -> Optional[List[float]]:
        """Generates 768-dimension vector embedding using free Gemini API if configured."""
        if not settings.GOOGLE_API_KEY:
            return None
        try:
            # We can use langchain_google_genai GoogleGenerativeAIEmbeddings
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            embedder = GoogleGenerativeAIEmbeddings(
                model=settings.EMBEDDING_MODEL,
                google_api_key=settings.GOOGLE_API_KEY
            )
            # Embed single text
            return await embedder.aembed_query(text)
        except Exception as e:
            logger.debug("Embedding generation skipped or failed: %s", str(e))
            return None
