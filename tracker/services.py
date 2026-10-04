import os
import json
from urllib.parse import quote_plus

import feedparser
import requests

MODEL = "openrouter/free"  # or the free model ID that worked for you


def fetch_layoff_news(limit=10):
    query = '(tech OR software OR "AI company" OR startup) layoffs when:3d'
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}"
    feed = feedparser.parse(url)
    return [{"title": e.title, "link": e.link} for e in feed.entries[:limit]]


PROMPT = """You are a tech-industry analyst writing a layoff briefing.

From the headlines below, keep ONLY layoffs at technology companies
(software, internet, AI, semiconductors, hardware, IT services, tech startups).
Ignore non-tech companies (retail, banks, airlines, media, etc.) and non-layoff news.

Reply with ONLY valid JSON, no markdown, in this exact shape:
{{
  "summary": "3 concise sentences on the overall trend",
  "layoffs": [
    {{
      "company": "name",
      "employees_affected": "number or 'Not disclosed'",
      "reason": "one short sentence or 'Not disclosed'",
      "link": "url from the headline"
    }}
  ]
}}

Rules: never invent numbers or reasons. If nothing qualifies, return an empty "layoffs" list.

Headlines:
{headlines}"""


def summarize(articles):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    headlines = "\n".join(f"- {a['title']} ({a['link']})" for a in articles)
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT.format(headlines=headlines)}],
            "max_tokens": 1500,
        },
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"OpenRouter {response.status_code}: {response.text}")

    content = response.json()["choices"][0]["message"]["content"]
    if not content:
        raise RuntimeError("Model returned an empty response")

    # strip ```json fences if the model adds them
    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"summary": content, "layoffs": []}  # fallback so it never crashes