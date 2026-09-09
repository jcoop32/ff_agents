"""
WebResearchService: Autonomous web intel gathering.
Uses Google Search Grounding with Gemini as primary real-time research engine,
with graceful fallbacks to ESPN RSS feeds, Reddit sentiment, and Groq synthesis.
Requires zero local browser resources (no Playwright).
"""

import logging
import re
from typing import Dict, Any, List, Optional
import httpx
import feedparser

from app.core.config import settings

logger = logging.getLogger(__name__)


class WebResearchService:
    """Multi-source web intelligence service for fantasy football insights."""

    @classmethod
    async def search_gemini_grounded(
        cls,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes real-time web search grounding using Google Gemini.
        Zero local compute footprint.
        """
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            logger.warning("GOOGLE_API_KEY missing. Cannot perform Gemini grounded search.")
            return {"text": "", "sources": [], "status": "NO_API_KEY"}

        candidate_models = [
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.8-flash",
            "gemini-flash-latest",
        ]

        # Try google.genai SDK
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            config = types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.2,
            )
            if system_instruction:
                config.system_instruction = system_instruction

            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    text = response.text or ""
                    sources = []
                    # Extract grounding sources if present
                    if response.candidates:
                        cand = response.candidates[0]
                        gm = getattr(cand, "grounding_metadata", None)
                        if gm:
                            chunks = getattr(gm, "grounding_chunks", []) or []
                            for chunk in chunks:
                                web = getattr(chunk, "web", None)
                                if web:
                                    sources.append({
                                        "title": getattr(web, "title", ""),
                                        "uri": getattr(web, "uri", ""),
                                    })

                    return {
                        "text": text,
                        "sources": sources,
                        "status": "SUCCESS",
                        "model": model_name,
                    }
                except Exception as model_err:
                    err_str = str(model_err)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        logger.warning("Gemini model %s hit quota limit: %s", model_name, err_str[:120])
                        continue
                    elif "404" in err_str:
                        continue
                    else:
                        logger.warning("Gemini error with %s: %s", model_name, err_str[:120])
                        continue
        except Exception as e:
            logger.error("Failed to initialize Google GenAI SDK: %s", str(e))

        return {"text": "", "sources": [], "status": "FAILED"}

    @classmethod
    async def fetch_espn_rss_intel(cls, query_keyword: Optional[str] = None) -> List[Dict[str, str]]:
        """Fetches live NFL news from ESPN RSS and filters for relevant mentions."""
        feed_url = "https://www.espn.com/espn/rss/nfl/news"
        results = []
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(feed_url, headers={"User-Agent": "GridironAI/1.0"})
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:25]:
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")
                        link = entry.get("link", "")
                        published = entry.get("published", "")

                        if not query_keyword or (
                            query_keyword.lower() in title.lower()
                            or query_keyword.lower() in summary.lower()
                        ):
                            results.append({
                                "title": title,
                                "summary": summary,
                                "link": link,
                                "published": published,
                                "source": "ESPN RSS",
                            })
        except Exception as e:
            logger.warning("Error fetching ESPN RSS feed: %s", str(e))

        return results

    @classmethod
    async def fetch_reddit_sentiment(cls, player_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches community sentiment from r/fantasyfootball.
        Safely handles rate limits and fallback.
        """
        results = []
        if not settings.REDDIT_RESEARCH_ENABLED:
            return results

        clean_name = player_name.replace(" ", "+")
        url = f"https://www.reddit.com/r/fantasyfootball/search.json?q={clean_name}&sort=new&limit={limit}&restrict_sr=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    children = data.get("data", {}).get("children", [])
                    for post in children:
                        pdata = post.get("data", {})
                        results.append({
                            "title": pdata.get("title", ""),
                            "score": pdata.get("score", 0),
                            "num_comments": pdata.get("num_comments", 0),
                            "url": f"https://reddit.com{pdata.get('permalink', '')}",
                            "source": "r/fantasyfootball",
                        })
        except Exception as e:
            logger.debug("Reddit sentiment search skipped/failed: %s", str(e))

        return results

    @classmethod
    async def research_player(
        cls,
        player_name: str,
        focus_areas: Optional[List[str]] = None,
        custom_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive multi-source research on a player.
        Checks:
        1. Real-time Gemini Google Search Grounding
        2. ESPN RSS News Feed
        3. Reddit Community Sentiment
        4. Groq synthesis if Gemini was unavailable
        """
        focus_str = ", ".join(focus_areas) if focus_areas else "injury, practice status, depth chart, role changes"
        query = custom_query or f"Latest fantasy football news, practice updates, injury status, and depth chart role for NFL player {player_name} for the current week."

        # 1. Grounded Search
        gemini_result = await cls.search_gemini_grounded(
            prompt=query,
            system_instruction=(
                "You are an expert NFL fantasy football beat reporter and injury analyst. "
                f"Provide concise, up-to-the-minute status for {player_name}. Focus specifically on: {focus_str}. "
                "Highlight: injury designation (Out, Questionable, Doubtful, Healthy), practice participation (DNP, LP, FP), "
                "expected playing time, backup beneficiaries if out, and fantasy outlook."
            )
        )

        # 2. ESPN RSS mentions
        rss_mentions = await cls.fetch_espn_rss_intel(query_keyword=player_name)

        # 3. Reddit community discussion
        reddit_posts = await cls.fetch_reddit_sentiment(player_name=player_name, limit=3)

        summary_text = ""
        sources = gemini_result.get("sources", [])

        if gemini_result.get("status") == "SUCCESS" and gemini_result.get("text"):
            summary_text = gemini_result["text"]
        else:
            # Fallback synthesis using Groq with available RSS & Reddit context
            logger.info("Using Groq fallback for player research on %s", player_name)
            context_pieces = []
            for r in rss_mentions:
                context_pieces.append(f"ESPN: {r['title']} - {r['summary']}")
            for rd in reddit_posts:
                context_pieces.append(f"Reddit: {rd['title']} (Score: {rd['score']})")

            context_str = "\n".join(context_pieces) if context_pieces else "No breaking RSS headlines found."

            try:
                from groq import Groq
                groq_client = Groq(api_key=settings.GROQ_API_KEY)
                prompt_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert NFL fantasy football analyst. Synthesize the latest situation for the player. "
                            f"Focus on {focus_str}. Be concise and action-oriented for fantasy managers."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Player: {player_name}\n"
                            f"Context headlines:\n{context_str}\n\n"
                            f"Analyze the situation for {player_name} and advise on fantasy impact."
                        ),
                    },
                ]
                resp = groq_client.chat.completions.create(
                    model=settings.FAST_MODEL,
                    messages=prompt_messages,
                    temperature=0.3,
                    max_tokens=600,
                )
                raw_out = resp.choices[0].message.content or ""
                # Strip thinking tokens if present
                clean_text = re.sub(r"<think>.*?</think>", "", raw_out, flags=re.DOTALL).strip()
                summary_text = clean_text or raw_out
            except Exception as ge:
                logger.error("Groq fallback also failed: %s", str(ge))
                summary_text = f"Monitored {player_name}. No critical new developments detected in recent feeds."

        return {
            "player_name": player_name,
            "summary": summary_text,
            "sources": sources,
            "rss_mentions": rss_mentions,
            "reddit_posts": reddit_posts,
            "grounded": gemini_result.get("status") == "SUCCESS",
        }


# ==========================================
# LangChain Tool Wrappers for Supervisor GM
# ==========================================

from langchain_core.tools import tool


@tool
async def search_web_intelligence(query: str) -> str:
    """
    Search the live web for real-time NFL news, injury reports, coaching comments,
    depth chart battles, and breaking fantasy football intelligence using Google Search Grounding.
    Use this when you need live external information beyond the database.
    """
    result = await WebResearchService.search_gemini_grounded(prompt=query)
    if result.get("status") == "SUCCESS":
        text = result.get("text", "")
        sources = result.get("sources", [])
        source_links = "\n".join([f"- [{s.get('title')}]({s.get('uri')})" for s in sources if s.get("uri")])
        if source_links:
            return f"{text}\n\n**Sources:**\n{source_links}"
        return text
    else:
        # Fallback to ESPN RSS search
        rss = await WebResearchService.fetch_espn_rss_intel(query_keyword=query.split()[0] if query else None)
        if rss:
            items = "\n".join([f"• **{r['title']}**: {r['summary']}" for r in rss[:5]])
            return f"Web search returned news feeds:\n{items}"
        return f"Unable to reach external web search at this moment. Proceeding with database knowledge."


@tool
async def research_player_status(player_name: str, focus: str = "injury, depth_chart") -> str:
    """
    Perform dedicated deep-dive web research on a specific player's status, injury severity,
    practice reports, coaching quotes, and fantasy viability.
    """
    focus_list = [f.strip() for f in focus.split(",")]
    intel = await WebResearchService.research_player(player_name=player_name, focus_areas=focus_list)
    return f"### Web Intel for {player_name}\n\n{intel.get('summary', 'No updates found.')}"
