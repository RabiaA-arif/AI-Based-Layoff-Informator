import json
from unittest.mock import Mock, patch

from django.core import mail
from django.template.loader import render_to_string
from django.test import TestCase, override_settings

from tracker import services
from tracker.models import EmailLog

DATA = {
    "summary": "Layoff activity stayed steady across software this week.",
    "layoffs": [
        {
            "company": "Acme Corp",
            "employees_affected": "120",
            "reason": "Restructuring",
            "link": "https://example.com/acme",
        }
    ],
}
EMPTY = {"summary": "Nothing notable this week.", "layoffs": []}


class TemplateTests(TestCase):
    def test_both_digest_templates_exist_and_render(self):
        for name in ("email_digest.html", "email_digest.txt"):
            with self.subTest(template=name):
                self.assertIn("Acme Corp", render_to_string(name, DATA))

    def test_plaintext_part_contains_no_markup(self):
        text = render_to_string("email_digest.txt", DATA)
        self.assertNotIn("<div", text)
        self.assertNotIn("<table", text)
        self.assertNotIn("&middot;", text)

    def test_plaintext_part_does_not_leak_html_entities(self):
        payload = {
            "summary": "Sam Altman's firm & others",
            "layoffs": [
                {
                    "company": "Sam Altman's eye-scanning co",
                    "employees_affected": "10 & 20",
                    "reason": "cost cutting <cut>",
                    "link": "https://example.com/a?b=1&c=2",
                }
            ],
        }
        text = render_to_string("email_digest.txt", payload)
        self.assertIn("Sam Altman's eye-scanning co", text)
        self.assertIn("10 & 20", text)
        self.assertIn("cost cutting <cut>", text)
        self.assertIn("b=1&c=2", text)
        for entity in ("&#x27;", "&amp;", "&lt;", "&gt;"):
            self.assertNotIn(entity, text)

    def test_html_part_still_escapes_model_supplied_text(self):
        payload = {
            "summary": "Sam Altman's firm",
            "layoffs": [
                {"company": "A & B", "employees_affected": "1", "reason": "r", "link": ""}
            ],
        }
        html = render_to_string("email_digest.html", payload)
        self.assertIn("Sam Altman&#x27;s firm", html)
        self.assertIn("A &amp; B", html)

    def test_templates_render_when_there_are_no_layoffs(self):
        for name in ("email_digest.html", "email_digest.txt"):
            with self.subTest(template=name):
                self.assertIn("No new tech layoffs", render_to_string(name, EMPTY))

    def test_html_escapes_model_supplied_text(self):
        html = render_to_string(
            "email_digest.html", {"summary": "<script>alert(1)</script>", "layoffs": []}
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
)
class HomeViewTests(TestCase):
    # views.py does `from .services import fetch_layoff_news, summarize`, so the
    # names must be patched where the view looks them up, not on the source module.
    def test_post_sends_multipart_email_and_logs_success(self):
        with patch("tracker.views.fetch_layoff_news", return_value=[{"title": "t", "link": "u"}]), \
             patch("tracker.views.summarize", return_value=DATA):
            response = self.client.post("/", {"email": "reader@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["reader@example.com"])
        self.assertEqual(len(message.alternatives), 1)
        self.assertEqual(message.alternatives[0][1], "text/html")
        self.assertIn("Acme Corp", message.body)
        self.assertNotIn("<table", message.body)

        log = EmailLog.objects.get()
        self.assertEqual((log.email, log.status, log.layoffs_count), ("reader@example.com", "sent", 1))

    def test_failure_is_logged_and_surfaced(self):
        with patch("tracker.views.fetch_layoff_news", return_value=[]), \
             patch("tracker.views.summarize", side_effect=RuntimeError("boom")):
            response = self.client.post("/", {"email": "reader@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EmailLog.objects.get().status, "failed")


class ExtractJsonTests(TestCase):
    def test_variants(self):
        payload = {"summary": "s", "layoffs": []}
        for label, raw in {
            "bare": json.dumps(payload),
            "fenced": "```json\n" + json.dumps(payload) + "\n```",
            "prose then fence": "Here you go:\n```json\n" + json.dumps(payload) + "\n```",
            "prose no fence": "Sure! " + json.dumps(payload) + " Hope that helps.",
        }.items():
            with self.subTest(case=label):
                self.assertEqual(services._extract_json(raw), payload)

    def test_unparseable_returns_none(self):
        self.assertIsNone(services._extract_json("I could not find anything."))


class NormalizeTests(TestCase):
    def test_wrong_top_level_type_does_not_raise(self):
        for payload in (["a", "b"], "just a string", 42, None):
            with self.subTest(payload=payload):
                result = services._normalize(payload)
                self.assertIsInstance(result["summary"], str)
                self.assertEqual(result["layoffs"], [])

    def test_missing_fields_get_placeholders_and_bad_links_dropped(self):
        result = services._normalize(
            {"summary": "s", "layoffs": [{"company": "Acme", "link": "javascript:alert(1)"}]}
        )
        self.assertEqual(result["layoffs"][0]["employees_affected"], "Not disclosed")
        self.assertEqual(result["layoffs"][0]["reason"], "Not disclosed")
        self.assertEqual(result["layoffs"][0]["link"], "")

    def test_duplicate_companies_collapse_and_junk_entries_drop(self):
        result = services._normalize(
            {
                "summary": "s",
                "layoffs": [{"company": "Acme"}, "nope", {"company": "acme"}, {"company": ""}],
            }
        )
        self.assertEqual([item["company"] for item in result["layoffs"]], ["Acme"])


class CompletionBudgetTests(TestCase):
    """The free router serves reasoning models that return no content when the
    token budget is consumed by reasoning."""

    def _response(self, content="", finish_reason="length"):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": content}, "finish_reason": finish_reason}]
        }
        return response

    def test_retries_with_a_larger_budget_when_content_is_empty(self):
        post = Mock(side_effect=[self._response(), self._response('{"summary": "s", "layoffs": []}')])
        with patch.object(services.requests.Session, "post", post):
            content = services._request_completion("key", "prompt")

        self.assertIn("summary", content)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["max_tokens"], services.MAX_TOKENS)
        self.assertEqual(
            post.call_args_list[1].kwargs["json"]["max_tokens"], services.MAX_TOKENS * 2
        )
        self.assertEqual(
            post.call_args_list[0].kwargs["json"]["reasoning"], {"effort": "low"}
        )

    def test_gives_up_after_the_escalation_ceiling(self):
        post = Mock(return_value=self._response())
        with patch.object(services.requests.Session, "post", post), \
             self.assertRaises(RuntimeError):
            services._request_completion("key", "prompt")
        # starts at MAX_TOKENS, doubles once to the ceiling, then gives up
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[-1].kwargs["json"]["max_tokens"], services.MAX_TOKENS_CEILING
        )

    def test_empty_content_without_truncation_fails_immediately(self):
        post = Mock(return_value=self._response(content="", finish_reason="stop"))
        with patch.object(services.requests.Session, "post", post), \
             self.assertRaises(RuntimeError):
            services._request_completion("key", "prompt")
        self.assertEqual(post.call_count, 1)

    def test_reasoning_control_is_dropped_if_rejected(self):
        rejected = Mock(ok=False, status_code=400, text="unsupported reasoning control")
        post = Mock(side_effect=[rejected, self._response('{"summary": "s", "layoffs": []}')])
        with patch.object(services.requests.Session, "post", post):
            content = services._request_completion("key", "prompt")

        self.assertIn("summary", content)
        self.assertNotIn("reasoning", post.call_args_list[1].kwargs["json"])


class SummarizeTests(TestCase):
    def test_no_articles_skips_the_api_call(self):
        with patch.object(services, "_request_completion") as request:
            result = services.summarize([])
        request.assert_not_called()
        self.assertEqual(result["layoffs"], [])

    def test_non_json_reply_falls_back_to_summary_text(self):
        with patch.object(services, "_request_completion", return_value="no json here"):
            result = services.summarize([{"title": "t", "link": "u"}])
        self.assertEqual(result, {"summary": "no json here", "layoffs": []})


class FeedTests(TestCase):
    def test_link_safety(self):
        self.assertEqual(services._safe_link("javascript:alert(1)"), "")
        self.assertEqual(services._safe_link("https://example.com/x"), "https://example.com/x")
