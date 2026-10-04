import os

import feedparser
import requests


def fetch_layoff_news(limit=8):
    url = "https://news.google.com/rss/search?q=company+layoffs+when:3d"
    feed = feedparser.parse(url)
    return [{"title": entry.title, "link": entry.link} for entry in feed.entries[:limit]]


def summarize(articles):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    headlines = "\n".join(
        f"- {article['title']} ({article['link']})" for article in articles
    )
    prompt = f"""From these news headlines, extract company layoff information.
            For each real layoff give: company, number of employees affected (if known),
            reason (if known), and link. Then write a 3-sentence overall summary.
            Ignore irrelevant headlines.

{headlines}"""
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            # "model": "meta-llama/llama-3.3-70b-instruct:free",
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    # print(data)
    choices = data.get("choices")
    if not choices or not choices[0].get("message", {}).get("content"):
        error = data.get("error", {})
        detail = error.get("message") if isinstance(error, dict) else None
        if detail:
            raise RuntimeError(f"OpenRouter returned no summary: {detail}")
        raise RuntimeError("OpenRouter response did not contain a summary")

    return choices[0]["message"]["content"]
