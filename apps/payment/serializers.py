from rest_framework import serializers

from apps.payment.models import Payment
from apps.subscriptions.models import Plan


class PaymentSerializer(serializers.ModelSerializer):

    plan_name = serializers.CharField(
        source="plan.name",
        read_only=True,
    )

    class Meta:
        model = Payment

        fields = (
            "id",
            "plan",
            "plan_name",
            "amount",
            "currency",
            "payment_method",
            "status",
            "stripe_checkout_session_id",
            "stripe_payment_intent_id",
            "stripe_customer_id",
            "stripe_invoice_id",
            "transaction_id",
            "paid_at",
            "failure_reason",
            "refund_reason",
            "metadata",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "amount",
            "currency",
            "payment_method",
            "status",
            "stripe_checkout_session_id",
            "stripe_payment_intent_id",
            "stripe_customer_id",
            "stripe_invoice_id",
            "transaction_id",
            "paid_at",
            "failure_reason",
            "refund_reason",
            "metadata",
            "created_at",
            "updated_at",
        )

        extra_kwargs = {

            "plan": {
                "error_messages": {
                    "required": "Please select a subscription plan.",
                    "null": "Plan cannot be null.",
                    "does_not_exist": "Selected plan does not exist.",
                }
            }
        }

    # -------------------------------------------------
    # PLAN VALIDATION
    # -------------------------------------------------

    def validate_plan(self, value):

        if not value.is_active:
            raise serializers.ValidationError(
                "This subscription plan is currently unavailable."
            )

        if value.price <= 0:
            raise serializers.ValidationError(
                "Invalid subscription plan."
            )

        if not value.stripe_price_id:
            raise serializers.ValidationError(
                "Stripe Price ID is missing for this plan."
            )

        return value

    # -------------------------------------------------
    # OBJECT VALIDATION
    # -------------------------------------------------

    def validate(self, attrs):

        request = self.context["request"]

        user = request.user

        if not user.is_verified:
            raise serializers.ValidationError({
                "detail": "Please verify your account first."
            })

        if not hasattr(user, "profile"):
            raise serializers.ValidationError({
                "detail": "Please complete your profile first."
            })

        if not hasattr(user, "kyc"):
            raise serializers.ValidationError({
                "detail": "Please complete KYC verification first."
            })

        if user.kyc.status != "APPROVED":
            raise serializers.ValidationError({
                "detail": "Your KYC has not been approved yet."
            })

        return attrs