from django.db import models


class Question(models.Model):
    text = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:60]


class ModelResponse(models.Model):
    """One contestant model's answer to a Question."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="responses")
    model_id = models.CharField(max_length=120)        # e.g. "ollama:llama3.2:1b"
    display_name = models.CharField(max_length=120)    # e.g. "Llama 3.2 1B"
    response = models.TextField(blank=True)
    error = models.TextField(blank=True, null=True)
    latency_ms = models.IntegerField(default=0)
    is_winner = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    verdict = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.model_id} -> Q{self.question_id}"


class Judgment(models.Model):
    """The independent judge's evaluation of all responses to a Question."""

    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name="judgment")
    winner_model_id = models.CharField(max_length=120, blank=True, null=True)
    reason = models.TextField(blank=True)
    consensus = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Judgment for Q{self.question_id}"
