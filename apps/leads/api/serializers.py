from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.analytics.api.serializers import LeadScoreSerializer
from apps.leads.forms import LeadForm
from apps.leads.models import Lead, LeadItem


class LeadItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeadItem
        fields = [
            "id",
            "product_id",
            "product_name",
            "category_name",
            "product_slug",
            "product_url",
            "quantity",
            "product_price",
            "line_total",
            "snapshot",
            "created_at",
        ]


class LeadScoreSummarySerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=6, decimal_places=2)
    priority = serializers.CharField()
    model_name = serializers.CharField()
    model_version = serializers.CharField()
    predicted_at = serializers.DateTimeField()


class LeadListSerializer(serializers.ModelSerializer):
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    items_count = serializers.IntegerField(read_only=True)
    total_quantity = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    score_summary = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "source",
            "source_label",
            "status",
            "status_label",
            "fullname",
            "email",
            "phone_number",
            "items_count",
            "total_quantity",
            "total_amount",
            "score_summary",
            "created_at",
            "updated_at",
        ]

    def get_score_summary(self, obj: Lead) -> dict | None:
        try:
            score = obj.score
        except ObjectDoesNotExist:
            return None

        return {
            "score": str(score.score),
            "priority": score.priority,
            "model_name": score.model_name,
            "model_version": score.model_version,
            "predicted_at": score.predicted_at,
        }


class LeadDetailSerializer(LeadListSerializer):
    items = LeadItemSerializer(many=True, read_only=True)
    score = LeadScoreSerializer(read_only=True)

    processed_by_username = serializers.CharField(
        source="processed_by.username",
        read_only=True,
    )

    class Meta(LeadListSerializer.Meta):
        fields = [
            *LeadListSerializer.Meta.fields,
            "comment",
            "source_path",
            "referer",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "manager_comment",
            "processed_by",
            "processed_by_username",
            "processed_at",
            "items",
            "score",
        ]


class LeadContactCreateSerializer(serializers.Serializer):
    fullname = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    comment = serializers.CharField(required=False, allow_blank=True)
    agree_to_policy = serializers.BooleanField(write_only=True)

    def validate_agree_to_policy(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError(
                "Необходимо согласие на обработку персональных данных."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        """
        Reuse existing Django LeadForm validation so HTML forms and API forms
        follow the same validation rules.
        """
        form = LeadForm(data=attrs)

        if not form.is_valid():
            raise serializers.ValidationError(form.errors.get_json_data())

        attrs["_form"] = form
        return attrs

class LeadCreateResponseSerializer(serializers.ModelSerializer):
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    message = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "source",
            "source_label",
            "status",
            "status_label",
            "message",
            "created_at",
        ]

    def get_message(self, obj: Lead) -> str:
        return "Lead created successfully."