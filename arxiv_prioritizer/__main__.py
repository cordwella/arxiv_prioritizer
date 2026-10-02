from __future__ import annotations

import argparse

from arxiv_prioritizer.arxiv_client import fetch_arxiv_papers
from arxiv_prioritizer.config import Config
from arxiv_prioritizer.notifier import build_notification_message, send_mattermost_message
from arxiv_prioritizer.ranker import select_top_papers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and prioritize arXiv astronomy papers.")
    parser.add_argument("--category", default="astro-ph", help="arXiv category, e.g. astro-ph")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back")
    parser.add_argument("--top-n", type=int, default=5, help="Number of papers to send")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Limit the arXiv fetch to 20 papers for a quicker test run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = Config.from_env()
    config.arxiv_category = args.category or config.arxiv_category
    config.arxiv_window_days = args.days or config.arxiv_window_days
    config.top_n = args.top_n or config.top_n

    papers = fetch_arxiv_papers(
        category=config.arxiv_category,
        days=config.arxiv_window_days,
        max_results=20 if args.debug else None,
    )
    if not papers:
        message = f"No papers found in category {config.arxiv_category} in the last {config.arxiv_window_days} days."
        send_mattermost_message(config.mattermost_webhook_url, message)
        return

    top_papers = select_top_papers(papers, config.user_profile, config.top_n)
    message = build_notification_message(top_papers, config.arxiv_category)
    send_mattermost_message(config.mattermost_webhook_url, message)


if __name__ == "__main__":
    main()
