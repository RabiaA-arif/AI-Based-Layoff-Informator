import json
import logging
import os
import re
import time
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

logger = logging.getLogger(__name__)

MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

REQUEST_TIMEOUT = 10
SUMMARY_TIMEOUT = 60
FEED_ATTEMPTS = 2
MAX_ATTEMPTS = 3
RETRY_BACKOFF = 2
MAX_TOKENS = 8000
MAX_TOKENS_CEILING = 16000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

QUERY = "(tech OR software OR AI OR startup) layoffs when:3d"
BING_QUERY = "(tech OR software OR AI OR startup) layoffs"

FEEDS = {
    "Google News": (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(QUERY)}&hl=en-US&gl=US&ceid=US:en"
    ),
    "Bing News": f"https://www.bing.com/news/search?q={quote_plus(BING_QUERY)}&format=rss",
    "TechCrunch": "https://techcrunch.com/tag/layoffs/feed/",
    "Hacker News": "https://hnrss.org/newest?q=layoffs&count=15",
}

KEYWORDS = ("layoff", "laid off", "job cuts", "cuts jobs", "redundan",
            "workforce reduction", "downsiz")

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
NOT_DISCLOSED = "Not disclosed"
EMPTY_SUMMARY = "No tech layoff headlines matched the tracked sources in this run."


def _clean_text(value):
    if value is None or isinstance(value, (dict, list, tuple)):
        return ""
    return " ".join(str(value).split())


def _safe_link(value):
    link = _clean_text(value)
    parsed = urlparse(link)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return link
    return ""


def _load_feed(session, url):
    # feedparser never raises on network errors, so fetch the bytes ourselves:
    # that gives us a real timeout, real status codes, and a real failure signal.
    for attempt in range(1, FEED_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Attempt %s/%s failed for %s: %s", attempt, FEED_ATTEMPTS, url, exc)
            if attempt == FEED_ATTEMPTS:
                return None
            time.sleep(RETRY_BACKOFF * attempt)
        else:
            return feedparser.parse(response.content)
    return None


def fetch_layoff_news(limit_per_source=5, max_total=15):
    articles, seen = [], set()
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        for source, url in FEEDS.items():
            feed = _load_feed(session, url)
            if feed is None:
                logger.warning("Skipping %s: feed could not be fetched", source)
                continue
            count = 0
            for entry in feed.entries:
                title = _clean_text(entry.get("title", ""))
                link = _safe_link(entry.get("link", ""))
                key = title.lower()[:60]  # simple duplicate check
                if not link or key in seen:
                    continue
                if not any(k in title.lower() for k in KEYWORDS):
                    continue
                seen.add(key)
                articles.append({"title": title, "link": link, "source": source})
                count += 1
                if count >= limit_per_source:
                    break
    if not articles:
        logger.warning("No matching layoff headlines collected; a feed may be down or empty")
    return articles[:max_total]


PROMPT = """You are a tech-industry analyst writing a layoff briefing.

From the headlines below, keep ONLY layoffs at technology companies
(software, internet, AI, semiconductors, hardware, IT services, tech startups).
Ignore non-tech companies (retail, banks, airlines, media, etc.) and non-layoff news.

Reply with ONLY valid JSON, no markdown, no commentary, in this exact shape:
{{
  "summary": "3 concise sentences on the overall trend",
  "layoffs": [
    {{
      "company": "name",
      "employees_affected": "number or 'Not disclosed'",
      "reason": "one short sentence or 'Not disclosed'",
      "link": "url copied exactly from the headline, or '' if absent"
    }}
  ]
}}

Rules: never invent numbers or reasons. Copy every link character-for-character
from the headline it came from. If nothing qualifies, return an empty "layoffs" list.

Headlines:
{headlines}"""


def _read_completion(response):
    try:
        choice = response.json()["choices"][0]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response shape: {exc}") from exc
    message = choice.get("message") or {}
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = ""
    return content, choice.get("finish_reason")


def _post_completion(session, headers, payload):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.post(
                OPENROUTER_URL, headers=headers, json=payload, timeout=SUMMARY_TIMEOUT
            )
        except requests.RequestException as exc:
            logger.warning("OpenRouter attempt %s/%s failed: %s", attempt, MAX_ATTEMPTS, exc)
        else:
            if response.ok:
                return _read_completion(response)
            if response.status_code == 400 and "reasoning" in payload:
                # some free models reject the reasoning control; drop it and retry once
                logger.warning("OpenRouter rejected the reasoning control; retrying without it")
                payload = {k: v for k, v in payload.items() if k != "reasoning"}
                continue
            if response.status_code not in RETRYABLE_STATUS:
                raise RuntimeError(f"OpenRouter {response.status_code}: {response.text[:500]}")
            logger.warning(
                "OpenRouter attempt %s/%s returned %s", attempt, MAX_ATTEMPTS, response.status_code
            )
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF * attempt)
    raise RuntimeError(f"OpenRouter request failed after {MAX_ATTEMPTS} attempts")


def _request_completion(api_key, prompt):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # The free router serves reasoning models that will happily spend the whole
    # token budget thinking and return no content at all (finish_reason="length").
    # Capping reasoning avoids that; the escalating retry covers models that ignore it.
    max_tokens = MAX_TOKENS
    escalations = 0
    with requests.Session() as session:
        while True:
            payload = {
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "reasoning": {"effort": "low"},
            }
            content, finish_reason = _post_completion(session, headers, payload)
            if content.strip():
                return content
            if finish_reason != "length" or escalations >= 2 or max_tokens >= MAX_TOKENS_CEILING:
                raise RuntimeError(
                    f"Model returned no content (finish_reason={finish_reason!r}, "
                    f"max_tokens={max_tokens})"
                )
            escalations += 1
            max_tokens = min(max_tokens * 2, MAX_TOKENS_CEILING)
            logger.warning(
                "Model spent its budget on reasoning; retrying with max_tokens=%s", max_tokens
            )


def _extract_json(content):
    # Models routinely wrap JSON in prose or fences, so try each plausible span
    # instead of assuming the whole reply is JSON.
    candidates = []
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1))
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        candidates.append(content[start : end + 1])
    candidates.append(content)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _normalize(payload):
    if not isinstance(payload, dict):
        return {"summary": _clean_text(payload) or EMPTY_SUMMARY, "layoffs": []}

    summary = _clean_text(payload.get("summary")) or EMPTY_SUMMARY

    layoffs, seen = [], set()
    raw = payload.get("layoffs")
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            company = _clean_text(entry.get("company"))
            if not company or company.lower() in seen:
                continue
            seen.add(company.lower())
            layoffs.append(
                {
                    "company": company,
                    "employees_affected": _clean_text(entry.get("employees_affected"))
                    or NOT_DISCLOSED,
                    "reason": _clean_text(entry.get("reason")) or NOT_DISCLOSED,
                    "link": _safe_link(entry.get("link")),
                }
            )
    return {"summary": summary, "layoffs": layoffs}


def summarize(articles):
    if not articles:
        return {"summary": EMPTY_SUMMARY, "layoffs": []}

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    headlines = "\n".join(f"- {a['title']} ({a['link']})" for a in articles)
    content = _request_completion(api_key, PROMPT.format(headlines=headlines))

    payload = _extract_json(content)
    if payload is None:
        # Never crash the send: fall back to using the raw reply as the summary.
        logger.warning("Model reply was not valid JSON; using it as summary text only")
        return {"summary": _clean_text(content)[:600] or EMPTY_SUMMARY, "layoffs": []}
    return _normalize(payload)
