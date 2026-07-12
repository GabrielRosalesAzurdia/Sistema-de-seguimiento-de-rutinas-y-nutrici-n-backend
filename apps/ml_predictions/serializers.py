from rest_framework import serializers
from .models import MLPrediction


class MLPredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLPrediction
        fields = "__all__"
        read_only_fields = ["created_at"]
