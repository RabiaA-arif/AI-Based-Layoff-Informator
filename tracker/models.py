from django.db import models

# Create your models here.


class EmailLog(models.Model):
    email = models.EmailField()
    layoffs_count = models.IntegerField(default=0)
    status = models.CharField(max_length=10)  # "sent" or "failed"
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email} - {self.status}"