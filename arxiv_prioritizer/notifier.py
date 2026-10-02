from __future__ import annotations

from typing import Iterable

import requests


def build_notification_message(papers: list[dict], category: str) -> str:
    if not papers:
        return f"No new *{category}* arXiv papers were found this week."

    lines = [
        f"*ArXiv {category} highlights*",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        line = (
            f"{index}. [{paper['title']}]({paper['url']})\n"
            f"   - Authors: {', '.join(paper['authors'][:5]) or 'Unknown'}\n"
            f"   - Summary: {paper['summary'][:220]}"
        )
        lines.append(line)
    return "\n".join(lines)


def send_mattermost_message(url: str, text: str) -> None:
    if not url:
        print("No Mattermost webhook URL provided. Skipping message send.")
        print(text)
        return

    try:
        response = requests.post(url, json={"text": text}, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending Mattermost message: {e}")
        print("Message content:")
        print(text)
