from rest_framework import serializers

from apps.analytics.models import LeadScore
from apps.analytics.services import SCORING_STATES, scoring_summary


class ScoringOperationErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()


class LeadScoringStatusSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=SCORING_STATES)
    has_result = serializers.BooleanField()
    is_stale = serializers.BooleanField()
    requested_revision = serializers.IntegerField(allow_null=True)
    completed_revision = serializers.IntegerField(allow_null=True)
    requested_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    error_code = serializers.CharField(allow_null=True)

    def to_representation(self, instance):
        return super().to_representation(scoring_summary(instance))


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
