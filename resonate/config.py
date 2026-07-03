import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int | None = None
    db_path: str = "resonate.db"
    idle_timeout: int = 300

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise SystemExit(
                "DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token."
            )
        guild_id = os.getenv("GUILD_ID", "").strip()
        return cls(
            token=token,
            guild_id=int(guild_id) if guild_id else None,
            db_path=os.getenv("DB_PATH", "resonate.db").strip() or "resonate.db",
            idle_timeout=int(os.getenv("IDLE_TIMEOUT", "300")),
        )
