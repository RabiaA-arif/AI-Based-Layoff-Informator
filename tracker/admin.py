from django.contrib import admin
from .models import EmailLog

# Register your models here.


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "layoffs_count", "sent_at")