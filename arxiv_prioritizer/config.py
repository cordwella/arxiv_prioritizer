from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    arxiv_category: str = "astro-ph"
    arxiv_window_days: int = 7
    top_n: int = 5
    user_profile: str = "I am interested in astro-physics, galaxy formation, black holes, and cosmology."
    doubleword_api_url: str | None = None
    doubleword_api_key: str | None = None
    mattermost_webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        return cls(
            arxiv_category=os.getenv("ARXIV_CATEGORY", "astro-ph"),
            arxiv_window_days=int(os.getenv("ARXIV_WINDOW_DAYS", "7")),
            top_n=int(os.getenv("ARXIV_TOP_N", "5")),
            user_profile=os.getenv(
                "USER_PROFILE",
                "I am interested in astro-physics, galaxy formation, black holes, and cosmology.",
            ),
            doubleword_api_url=os.getenv("DOUBLEWORD_API_URL"),
            doubleword_api_key=os.getenv("DOUBLEWORD_API_KEY"),
            mattermost_webhook_url=os.getenv("MATTERMOST_WEBHOOK_URL"),
        )
