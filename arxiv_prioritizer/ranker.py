from __future__ import annotations

import json
import logging
import os

import requests

MAX_AI_CANDIDATES = 50
MAX_COMPLETION_TOKENS = 4096
MAX_SUMMARY_CHARS = 700


def build_relevance_prompt(papers: list[dict], user_profile: str, limit: int) -> str:
    paper_lines = []
    for index, paper in enumerate(papers, start=1):
        paper_lines.append(
            f"{index}. {paper['title']}\n"
            f"   Authors: {', '.join(paper['authors'][:5]) or 'Unknown'}\n"
            f"   Summary: {paper['summary'][:MAX_SUMMARY_CHARS]}\n"
            f"   URL: {paper['url']}"
        )

    return f"""You are a research assistant. I am interested in the following topics: {user_profile}

Please rank the papers below by likelihood of relevance and importance to me. Return only valid JSON in this format:
[
  {{"title": "exact paper title", "reason": "brief explanation"}}
]
Do not include markdown fences or any text outside the JSON array.

Choose at most {limit} papers. Keep the reasons brief and grounded in the paper title and abstract.

Papers:
{chr(10).join(paper_lines)}
"""


def rank_papers_with_doubleword(papers: list[dict], user_profile: str, limit: int) -> list[str]:
    """Rank papers using a hosted 'doubleword' style AI endpoint.

    If no endpoint is configured, fall back to a lightweight heuristic ranking.
    """

    api_url = os.getenv("DOUBLEWORD_API_URL")
    if not api_url:
        return fallback_rank_papers(papers, user_profile, limit)
    if len(papers) > MAX_AI_CANDIDATES:
        paper_by_title = {paper["title"]: paper for paper in papers}
        candidate_titles = fallback_rank_papers(
            papers,
            user_profile,
            MAX_AI_CANDIDATES,
        )
        papers = [paper_by_title[title] for title in candidate_titles]

    api_url = api_url.rstrip("/")
    if api_url.endswith("/v1"):
        api_url = f"{api_url}/chat/completions"

    prompt = build_relevance_prompt(papers, user_profile, limit)
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("DOUBLEWORD_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": os.getenv("DOUBLEWORD_MODEL", "default"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": MAX_COMPLETION_TOKENS,
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.warning("Doubleword HTTP request failed; using fallback ranking: %s", exc)
        return fallback_rank_papers(papers, user_profile, limit)

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        logging.warning(
            "Doubleword returned a non-JSON HTTP response (status %s); using fallback ranking: %s",
            response.status_code,
            exc,
        )
        return fallback_rank_papers(papers, user_profile, limit)

    try:
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content")
        if not isinstance(content, str):
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                raise ValueError(
                    f"completion was truncated at {MAX_COMPLETION_TOKENS} tokens "
                    "before the model returned final content"
                )
            if message.get("reasoning_content"):
                raise ValueError("model returned reasoning content but no final message content")
            raise ValueError("model message content was not a string")
        titles = _parse_ranked_titles(content)
        if not titles:
            raise ValueError("model returned no paper titles")
        return titles[:limit]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logging.warning("Doubleword returned invalid ranked-paper output; using fallback ranking: %s", exc)
        return fallback_rank_papers(papers, user_profile, limit)


def _parse_ranked_titles(content: str) -> list[str]:
    """Extract the JSON array of ranked paper titles from model output."""
    decoder = json.JSONDecoder()
    for start, character in enumerate(content):
        if character != "[":
            continue
        try:
            parsed, _ = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [
                item["title"]
                for item in parsed
                if isinstance(item, dict) and isinstance(item.get("title"), str)
            ]
    raise ValueError("could not find a valid JSON array in model output")


def fallback_rank_papers(papers: list[dict], user_profile: str, limit: int) -> list[str]:
    """Fallback heuristic ranking based on topic keyword overlap."""

    print("Using keyword-based ranking.")

    profile_terms = {term.lower() for term in user_profile.replace("-", " ").split() if len(term) > 3}
    fallback_keywords = [
        keyword.strip().lower()
        for keyword in os.getenv(
            "FALLBACK_KEYWORDS",
            "black hole,galaxy,cosmology,supernova,neutron,star,planet",
        ).split(",")
        if keyword.strip()
    ]
    scored = []
    for paper in papers:
        text = f"{paper['title']} {paper['summary']}".lower()
        overlap = sum(1 for term in profile_terms if term in text)
        score = overlap + (0.1 if any(keyword in text for keyword in fallback_keywords) else 0)
        scored.append((score, paper["title"]))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [title for _, title in scored[:limit]]


def select_top_papers(papers: list[dict], user_profile: str, limit: int) -> list[dict]:
    ranked_titles = rank_papers_with_doubleword(papers, user_profile, limit)
    ranked_map = {paper["title"]: paper for paper in papers}
    selected = []
    for title in ranked_titles:
        paper = ranked_map.get(title)
        if paper is not None:
            selected.append(paper)
    for paper in papers:
        if paper["title"] not in {item["title"] for item in selected}:
            selected.append(paper)
            if len(selected) >= limit:
                break
    return selected[:limit]
