from rest_framework import serializers

from apps.analytics.models import LeadScore


class LeadScoreSerializer(serializers.ModelSerializer):
    lead_id = serializers.IntegerField(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = LeadScore
        fields = [
            "lead_id",
            "score",
            "priority",
            "priority_label",
            "model_name",
            "model_version",
            "features",
            "explanation",
            "predicted_at",
        ]
