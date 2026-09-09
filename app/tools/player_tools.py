"""
Player lookup and entity resolution tools.
Queries local Redis indexes (<5ms) and PostgreSQL.
"""

from typing import Dict, Any, Optional
from langchain_core.tools import tool
from app.core.redis_client import RedisRepository


@tool
async def resolve_player(name: str) -> Dict[str, Any]:
    """
    Resolves a player's common or misspelled name to their canonical ESPN ID and metadata.
    Use this first before calling other player-specific tools.
    """
    clean_name = name.strip()
    player_id = await RedisRepository.resolve_player_id(clean_name)
    if not player_id:
        return {
            "found": False,
            "query": clean_name,
            "message": f"Player '{clean_name}' not found in local index. Check spelling."
        }

    info = await RedisRepository.get_player_hash(player_id)
    return {
        "found": True,
        "player_id": player_id,
        "name": info.get("name", clean_name),
        "team": info.get("team", "FA"),
        "position": info.get("pos", "FLEX"),
        "status": info.get("status", "Healthy"),
        "bye_week": info.get("bye", "")
    }


@tool
async def get_player_info(player_id: str) -> Dict[str, Any]:
    """
    Retrieves full biographical and roster metadata for a player by their ID.
    """
    info = await RedisRepository.get_player_hash(player_id)
    if not info:
        return {"found": False, "player_id": player_id, "message": "Player ID not found in cache."}
    return {"found": True, **info}
