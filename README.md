# AI-Based Layoff Informator

> **A calm, source-linked tech layoff briefing delivered straight to your inbox.**

[![Django](https://img.shields.io/badge/Django-6.1%2B-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Hacktoberfest](https://img.shields.io/badge/Hacktoberfest-2026-FF6F61)](https://hacktoberfest.com/)

## The story behind the project

Layoffs are stressful enough without having to repeatedly search through dozens of news sites to find out what is happening in the technology industry. I built **AI-Based Layoff Informator** after seeing how anxious my roommate—who works in software development—became whenever layoff news started trending.

The goal is simple: help people stay informed **without doom-scrolling**. A user enters an email address, and the application collects recent technology layoff headlines, filters out unrelated stories, creates a concise AI-assisted briefing, and sends it in both HTML and plain-text email formats.

This project is designed to turn an overwhelming stream of news into a small, useful, source-linked update that people can check when they are ready.

## What the application does

1. **Collects recent headlines** from multiple feeds:
   - Google News
   - Bing News
   - TechCrunch
   - Hacker News
2. **Filters for technology layoff stories** using keywords such as `layoff`, `job cuts`, `workforce reduction`, and `downsizing`.
3. **Removes duplicate headlines** and limits the number of articles processed.
4. **Uses OpenRouter** to create a structured briefing containing:
   - A short overview of the current trend
   - Company names
   - Employees affected, when disclosed
   - Reported reason, when available
   - A link back to the original source
5. **Sends a multipart email** with both a styled HTML digest and an accessible plain-text version.
6. **Records delivery outcomes** in the database, including the recipient, number of layoff items, status, timestamp, and any error message.

## Why this is useful

| Problem | How the project helps |
| --- | --- |
| Layoff information is scattered across many sources | Aggregates several feeds in one workflow |
| Headlines can be repetitive or unrelated | Filters by technology and layoff-related keywords |
| Important details are difficult to scan quickly | Produces a consistent company/impact/reason format |
| AI summaries can be unreliable | Preserves source links and tells readers to verify the original article |
| Email content is not always accessible | Includes both HTML and plain-text alternatives |
| External services can fail | Adds timeouts, retries, fallback handling, and delivery logs |

## Main user flow

```text
User enters email
        |
        v
Django view receives the request
        |
        v
Fetch RSS/news feeds with retry handling
        |
        v
Filter and deduplicate tech layoff headlines
        |
        v
OpenRouter returns a structured JSON briefing
        |
        v
Render HTML + plain-text email
        |
        v
Send the briefing and log the result
```

## Technology stack

- **Python**
- **Django** — web application, forms, templates, email, and persistence
- **SQLite** — development database
- **Requests** — feed and API requests with timeouts
- **Feedparser** — RSS parsing
- **OpenRouter** — AI-assisted classification and summarization
- **HTML email + plain text** — compatible email delivery
- **Django TestCase and mocks** — automated tests for the workflow

## Project structure

```text
AI-Based-Layoff-Informator/
├── config/
│   ├── settings.py       # Django and email configuration
│   ├── urls.py           # Home and admin routes
│   ├── asgi.py
│   └── wsgi.py
├── tracker/
│   ├── models.py         # EmailLog model
│   ├── services.py       # Feed collection and AI summarization
│   ├── views.py          # Form submission and email workflow
│   ├── tests.py          # Automated tests
│   ├── migrations/
│   └── templates/
│       ├── home.html
│       ├── email_digest.html
│       └── email_digest.txt
├── manage.py
├── db.sqlite3            # Included development database
└── README.md
```

## Getting started locally

### 1. Clone the repository

```bash
git clone https://github.com/RabiaA-arif/AI-Based-Layoff-Informator.git
cd AI-Based-Layoff-Informator
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate       # Windows PowerShell
```

### 3. Install the dependencies

The repository currently does not include a `requirements.txt` file, so install the project dependencies directly:

```bash
pip install django python-dotenv requests feedparser
```

### 4. Create environment variables

Create a `.env` file in the project root. The `.env` file is ignored by Git and should never be committed.

```dotenv
# Required for AI summaries
OPENROUTER_API_KEY=your_openrouter_api_key

# Optional: choose another OpenRouter-compatible model
OPENROUTER_MODEL=openrouter/free

# SMTP settings (the defaults are configured for Gmail)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@example.com
EMAIL_HOST_PASSWORD=your_email_app_password
```

For Gmail, use an **App Password** rather than your normal account password. Make sure the account has SMTP access enabled.

### 5. Prepare the database

```bash
python manage.py migrate
```

### 6. Run the development server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser, enter an email address, and submit the form to request a briefing.

## Running tests

Run the automated test suite with:

```bash
python manage.py test
```

The tests cover:

- HTML and plain-text email rendering
- Escaping model-generated content in HTML
- Empty briefing behavior
- Successful email delivery and `EmailLog` creation
- Failure logging
- JSON extraction from different AI response formats
- Normalization of incomplete or duplicate AI records
- Retry behavior when a model consumes its token budget
- Safe handling of source links
- Avoiding an AI API call when no articles are available

## Configuration and behavior notes

- The current interface sends a briefing **on demand** when the form is submitted; it does not yet run as a scheduled daily newsletter.
- News feeds are external services and can be unavailable or rate-limited. Feed requests use timeouts and retries, and unavailable sources are skipped.
- AI output is normalized before it reaches the email template. Missing values become `Not disclosed`, invalid links are discarded, and duplicate companies are collapsed.
- The email explicitly reminds readers that the summary is AI-generated and that details should be verified at the linked source.
- This is a development-oriented project. Before production deployment, move `SECRET_KEY` and `DEBUG` into environment variables, configure `ALLOWED_HOSTS`, use a production database, add abuse/rate limiting, and protect recipient data appropriately.

## Privacy and responsible use

This project handles email addresses in order to send the requested briefing and stores delivery results in `EmailLog`. A production version should add clear consent, an unsubscribe mechanism, data-retention rules, and stronger access controls for logs.

The application is an information tool—not an employment, legal, or financial advice service. News can be incomplete or corrected after publication, so readers should always open and verify the original source.

## Hacktoberfest perspective

This project is a small but practical open-source contribution built around a real everyday problem: reducing the anxiety and time cost of staying informed about layoffs in tech.

It demonstrates how open-source tools can be combined into a complete workflow:

- Public RSS/news sources for discovery
- Django for a lightweight web experience
- OpenRouter for structured AI summarization
- Email standards for broad compatibility
- Automated tests for reliability and safer iteration

Potential next contributions include scheduled digests, user preferences by industry or region, unsubscribe support, stronger privacy controls, a richer dashboard, and additional trusted news sources.

## Future improvements

- Add scheduled daily or weekly delivery with Celery, cron, or a task queue
- Add email verification and one-click unsubscribe
- Allow users to select topics such as software, AI, semiconductors, or startups
- Add a searchable history of previous briefings
- Improve source ranking and article-level confidence indicators
- Add deployment documentation and a production-ready settings module
- Add observability for feed health and AI/API latency

## Contributing

Contributions are welcome. A simple workflow is:

```bash
git checkout -b feature/your-improvement
# make and test your changes
python manage.py test
git add .
git commit -m "Describe your improvement"
git push origin feature/your-improvement
```

Please keep changes focused, avoid committing secrets or local databases containing personal data, and include tests for new behavior where possible.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


## Author

Built by **RabiaA-arif** for Hacktoberfest, with the goal of helping anxious technology workers stay informed in a more focused and human-friendly way.

[View the repository on GitHub](https://github.com/RabiaA-arif/AI-Based-Layoff-Informator)



[Watch the AI-Based Layoff Informator demo](https://youtu.be/WvyyZVjem9E)
