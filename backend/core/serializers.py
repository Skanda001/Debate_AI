from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Question, ModelResponse, Judgment


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "date_joined"]



class ModelResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelResponse
        fields = [
            "id", "model_id", "display_name", "response", "error",
            "latency_ms", "is_winner", "score", "verdict", "created_at",
        ]


class JudgmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Judgment
        fields = ["id", "winner_model_id", "reason", "consensus", "created_at"]


class QuestionSerializer(serializers.ModelSerializer):
    responses = ModelResponseSerializer(many=True, read_only=True)
    judgment = JudgmentSerializer(read_only=True)
    parent_id = serializers.IntegerField(source="parent.id", read_only=True)

    class Meta:
        model = Question
        fields = ["id", "parent_id", "text", "is_pinned", "created_at", "responses", "judgment"]
