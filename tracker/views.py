from django.shortcuts import render
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from .models import EmailLog
from .services import fetch_layoff_news, summarize


def home(request):
    message = ""
    if request.method == "POST":
        email = request.POST.get("email")
        count = 0
        try:
            data = summarize(fetch_layoff_news())
            count = len(data.get("layoffs", []))
            text = render_to_string("email_digest.txt", data)
            html = render_to_string("email_digest.html", data)

            msg = EmailMultiAlternatives("Tech Layoff Briefing: latest updates", text, None, [email])
            msg.attach_alternative(html, "text/html")
            msg.send()

            EmailLog.objects.create(email=email, layoffs_count=count, status="sent")
            message = f"Briefing sent to {email}!"
        except Exception as e:
            EmailLog.objects.create(email=email, layoffs_count=count, status="failed", error=str(e))
            message = f"Something went wrong: {e}"

    sent_total = EmailLog.objects.filter(status="sent").count()
    return render(request, "home.html", {"message": message, "sent_total": sent_total})