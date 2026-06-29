from decimal import Decimal

from rest_framework import serializers
from django.utils import timezone
from rest_framework import serializers

from apps.subscriptions.models import Plan, Subscription
from apps.subscriptions.models import Plan


class PlanSerializer(serializers.ModelSerializer):

    class Meta:
        model = Plan

        fields = (
            "id",
            "name",
            "slug",
            "description",
            "price",
            "currency",
            "billing_cycle",
            "duration_days",
            "trial_days",
            "badge",
            "is_popular",
            "is_public",
            "is_active",
            "sort_order",
            "features",
            "stripe_product_id",
            "stripe_price_id",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )

        extra_kwargs = {

            "name": {
                "error_messages": {
                    "required": "Plan name is required.",
                    "blank": "Plan name cannot be empty.",
                }
            },

            "slug": {
                "error_messages": {
                    "required": "Slug is required.",
                    "blank": "Slug cannot be empty.",
                }
            },

            "price": {
                "error_messages": {
                    "required": "Price is required.",
                    "invalid": "Enter a valid price.",
                }
            },

            "currency": {
                "error_messages": {
                    "required": "Currency is required.",
                    "blank": "Currency cannot be empty.",
                }
            },

            "billing_cycle": {
                "error_messages": {
                    "required": "Billing cycle is required.",
                    "invalid_choice": "Invalid billing cycle.",
                }
            },

            "duration_days": {
                "error_messages": {
                    "required": "Duration is required.",
                    "invalid": "Enter a valid duration.",
                }
            },
        }

    # ----------------------------------
    # NAME
    # ----------------------------------

    def validate_name(self, value):

        value = value.strip()

        queryset = Plan.objects.filter(name__iexact=value)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "A plan with this name already exists."
            )

        return value

    # ----------------------------------
    # SLUG
    # ----------------------------------

    def validate_slug(self, value):

        value = value.strip().lower()

        queryset = Plan.objects.filter(slug=value)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "This slug is already in use."
            )

        return value

    # ----------------------------------
    # PRICE
    # ----------------------------------

    def validate_price(self, value):

        if value < Decimal("0.00"):
            raise serializers.ValidationError(
                "Price cannot be negative."
            )

        return value

    # ----------------------------------
    # DURATION
    # ----------------------------------

    def validate_duration_days(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Duration must be greater than zero."
            )

        return value

    # ----------------------------------
    # TRIAL
    # ----------------------------------

    def validate_trial_days(self, value):

        if value < 0:
            raise serializers.ValidationError(
                "Trial days cannot be negative."
            )

        return value

    # ----------------------------------
    # FEATURES
    # ----------------------------------

    def validate_features(self, value):

        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Features must be a valid JSON object."
            )

        return value

    # ----------------------------------
    # OBJECT VALIDATION
    # ----------------------------------

    def validate(self, attrs):

        price = attrs.get(
            "price",
            self.instance.price if self.instance else Decimal("0.00")
        )

        trial_days = attrs.get(
            "trial_days",
            self.instance.trial_days if self.instance else 0
        )

        if price == Decimal("0.00") and trial_days > 0:
            raise serializers.ValidationError({
                "trial_days": "Free plans cannot have a trial period."
            })

        return attrs



# subscriptions serializers



class SubscriptionSerializer(serializers.ModelSerializer):

    plan_name = serializers.CharField(
        source="plan.name",
        read_only=True,
    )

    class Meta:
        model = Subscription

        fields = (
            "id",
            "plan",
            "plan_name",
            "status",
            "started_at",
            "expires_at",
            "cancelled_at",
            "auto_renew",
            "is_current",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "status",
            "cancelled_at",
            "is_current",
            "created_at",
            "updated_at",
        )

        extra_kwargs = {

            "plan": {
                "error_messages": {
                    "required": "Plan is required.",
                    "null": "Please select a plan.",
                    "does_not_exist": "Selected plan does not exist.",
                }
            },

            "started_at": {
                "error_messages": {
                    "required": "Subscription start date is required.",
                    "invalid": "Enter a valid datetime.",
                }
            },

            "expires_at": {
                "error_messages": {
                    "required": "Subscription expiry date is required.",
                    "invalid": "Enter a valid datetime.",
                }
            },
        }

    # -----------------------------------
    # PLAN VALIDATION
    # -----------------------------------

    def validate_plan(self, plan):

        if not plan.is_active:
            raise serializers.ValidationError(
                "This subscription plan is not available."
            )

        return plan

    # -----------------------------------
    # OBJECT VALIDATION
    # -----------------------------------

    def validate(self, attrs):

        request = self.context["request"]
        user = request.user

        started_at = attrs.get("started_at")
        expires_at = attrs.get("expires_at")

        if started_at and expires_at:
            if expires_at <= started_at:
                raise serializers.ValidationError({
                    "expires_at": "Expiry date must be after start date."
                })

        # Only one active/current subscription
        if not self.instance:
            active_subscription = Subscription.objects.filter(
                user=user,
                is_current=True,
            ).exists()

            if active_subscription:
                raise serializers.ValidationError({
                    "detail": "You already have an active subscription."
                })

        return attrs

    # -----------------------------------
    # CREATE
    # -----------------------------------

    def create(self, validated_data):

        validated_data["user"] = self.context["request"].user

        return Subscription.objects.create(**validated_data)

    # -----------------------------------
    # UPDATE
    # -----------------------------------

    def update(self, instance, validated_data):

        if instance.status == "CANCELLED":
            raise serializers.ValidationError({
                "detail": "Cancelled subscriptions cannot be updated."
            })

        return super().update(instance, validated_data)