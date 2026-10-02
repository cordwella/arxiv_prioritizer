# Arxiv-priortizer

A mostly vibe coded project to notify me about the most relevant arXiv postings on my work Mattermost every week to ensure that I don't miss things.

## Process:

1. Get a list of all of today's (or this week's) postings from arXiv astro-ph (configurable)
2. Use an AI (via a configurable Doubleword/OpenAI-compatible API) to identify the N papers most likely to be relevant to me or that I may have missed in my morning skim
3. Message me/a specific channel on Mattermost with a list of papers

This should be able to be run as a cron job.

## Python implementation

A runnable Python implementation has been added under the project package:

- `main.py` entry point
- `arxiv_prioritizer/config.py` for environment configuration
- `arxiv_prioritizer/arxiv_client.py` for arXiv RSS/API queries
- `arxiv_prioritizer/ranker.py` for relevance filtering
- `arxiv_prioritizer/notifier.py` for posting to Mattermost

## Setup

1. Copy `.env.example` to `.env` and fill in your values. `main.py` loads this
   project-root `.env` automatically at startup; variables already set in the
   process environment take precedence.
2. Install dependencies:
   `python3 -m pip install -r requirements.txt`
3. Run the job:
   `python3 main.py`

`FALLBACK_KEYWORDS` is a comma-separated list used by the heuristic ranker when
the AI endpoint is not configured or fails. Papers mentioning any configured
keyword receive a small relevance bonus; the fallback ranker also scores
overlap with `USER_PROFILE`. For example:

```dotenv
FALLBACK_KEYWORDS=galaxy,black hole,cosmology,simulation,astrophysics
```

For Doubleword, set `DOUBLEWORD_API_URL` to
`https://api.doubleword.ai/v1/chat/completions`. The ranker also accepts the
base URL `https://api.doubleword.ai/v1` and appends `/chat/completions`.
To keep requests manageable, it narrows large weekly result sets to 50
keyword-relevant candidates before asking Doubleword to rank them.

Optional arguments:

- `--category astro-ph`
- `--days 7`
- `--top-n 5`
- `--debug` to limit the arXiv fetch to 20 papers for a quicker test run

Example:

`python3 main.py --category astro-ph --days 7 --top-n 5`

Debug example:

`python3 main.py --debug`

The arXiv API's terms require no more than one request every three seconds.
The client follows that interval between pages, identifies itself with a
User-Agent, and retries transient rate-limit/server errors with exponential
backoff while honoring `Retry-After`. Avoid repeatedly launching the job while
testing; this code does not attempt to bypass arXiv's rate limits.