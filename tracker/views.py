from django.shortcuts import render

# Create your views here.
from django.shortcuts import render
from django.core.mail import send_mail
from .services import fetch_layoff_news, summarize


def home(request):
    message = ""
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            summary = summarize(fetch_layoff_news())
            send_mail("Your Layoff Update", summary, None, [email])
            message = f"Summary sent to {email}!"
        except Exception as e:
            message = f"Something went wrong: {e}"
    return render(request, "home.html", {"message": message})