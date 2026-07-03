from rest_framework import serializers

from apps.payment.models import Payment
from apps.subscriptions.models import Plan
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from apps.bookings.models import Booking
from .models import BookingPayment, BookingPaymentGateway, BookingPaymentStatus


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




# booking payment serializer


class BookingPaymentSerializer(serializers.ModelSerializer):
    """
    Production-optimized serializer for tracking escrow transactions.
    Bypasses SerializerMethodField performance bottlenecks via explicit source mapping.
    """
    # Normalized Booking contexts
    booking_status = serializers.CharField(source="booking.status", read_only=True)
    package_title = serializers.CharField(source="booking.package.title", read_only=True)
    
    # Counter-party informational mapping strings
    payer_email = serializers.EmailField(source="payer.email", read_only=True)
    payee_email = serializers.EmailField(source="payee.email", read_only=True)

    class Meta:
        model = BookingPayment
        fields = [
            "id",
            "booking",
            "booking_status",
            "package_title",
            "payer",
            "payer_email",
            "payee",
            "payee_email",
            "amount",
            "platform_fee",
            "currency",
            "gateway",
            "status",
            "provider_payment_id",
            "checkout_url",
            "transaction_id",
            "failure_reason",
            "created_at",
            "updated_at",
            "authorized_at",
            "captured_at",
            "refunded_at",
        ]
        read_only_fields = [
            "id",
            "payer",
            "payee",
            "amount",
            "platform_fee",
            "currency",
            "status",
            "provider_payment_id",
            "checkout_url",
            "transaction_id",
            "failure_reason",
            "authorized_at",
            "captured_at",
            "refunded_at",
        ]


# class InitiateBookingPaymentSerializer(serializers.Serializer):
#     """
#     Lightweight write-only input serializer designed to capture and strictly validate
#     inbound payment checkout session initializations.
#     """
#     booking_id = serializers.UUIDField(required=True)
#     gateway = serializers.ChoiceField(choices=BookingPaymentGateway.choices, default=BookingPaymentGateway.STRIPE)

#     def validate_booking_id(self, value):
#         """
#         Enforces strict enterprise business logic guards before hitting external payment APIs.
#         """
#         try:
#             # Pull along relations at the SQL layer to prevent N+1 checks down the line
#             booking = Booking.objects.select_related("package", "trip").get(id=value)
#         except Booking.DoesNotExist:
#             raise serializers.ValidationError(_("The requested booking profile instance does not exist."))

#         # 1. Ownership Guard: Only the person who sent the package can pay for it
#         request_user = self.context["request"].user
#         if booking.package.sender != request_user:
#             raise serializers.ValidationError(
#                 _("Access Denied. Only the designated package sender can initiate payment collections.")
#             )

#         # 2. State Guard: Prevent processing payments for already settled or inactive bookings
#         if hasattr(booking, "booking_payment"):
#             existing_payment = booking.booking_payment
#             if existing_payment.status in [BookingPaymentStatus.AUTHORIZED, BookingPaymentStatus.CAPTURED]:
#                 raise serializers.ValidationError(
#                     _("A verified successful escrow deposit already securely locks this booking contract.")
#                 )

#         # 3. Financial Integrity Guard: Ensure the pricing values have been calculated properly
#         reward_amount = getattr(booking, "agreed_reward", None)
#         if reward_amount is None or reward_amount <= 0:
#             raise serializers.ValidationError(
#                 _("Transaction aborted. Booking contains an invalid or zero-valued financial reward amount structure.")
#             )

#         # Cache the validated database record in the serializer instance memory context 
#         # so our future View/Service layers can grab it directly without a second SQL query.
#         self.context["booking_instance"] = booking
#         return value
    
class InitiateBookingPaymentSerializer(serializers.Serializer):
    """
    Lightweight write-only input serializer designed to capture and strictly validate
    inbound payment checkout session initializations.
    """
    booking_id = serializers.UUIDField(required=True)
    gateway = serializers.ChoiceField(choices=BookingPaymentGateway.choices, default=BookingPaymentGateway.STRIPE)

    def validate(self, attrs):
        """
        Enforces strict enterprise business logic guards before hitting external payment APIs.
        """
        booking_id_value = attrs.get("booking_id")

        try:
            # Pull along relations at the SQL layer to prevent N+1 checks down the line
            booking = Booking.objects.select_related("package", "trip").get(id=booking_id_value)
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"booking_id": _("The requested booking profile instance does not exist.")})

        # 1. Ownership Guard: Only the person who sent the package can pay for it
        request_user = self.context["request"].user
        if booking.package.sender != request_user:
            raise serializers.ValidationError(
                _("Access Denied. Only the designated package sender can initiate payment collections.")
            )

        # 2. State Guard: Prevent processing payments for already settled or inactive bookings
        if hasattr(booking, "booking_payment"):
            existing_payment = booking.booking_payment
            if existing_payment.status in [BookingPaymentStatus.AUTHORIZED, BookingPaymentStatus.CAPTURED]:
                raise serializers.ValidationError(
                    _("A verified successful escrow deposit already securely locks this booking contract.")
                )

        # 3. Financial Integrity Guard: Ensure the pricing values have been calculated properly
        reward_amount = getattr(booking, "agreed_reward", None)
        if reward_amount is None or reward_amount <= 0:
            raise serializers.ValidationError(
                _("Transaction aborted. Booking contains an invalid or zero-valued financial reward amount structure.")
            )

        # 🟢 FIX: Return the fully fetched booking object in validated_data for your view layer
        attrs["booking"] = booking
        return attrs


# payment history serializersfrom rest_framework import serializers
class BookingPaymentHistorySerializer(serializers.ModelSerializer):
    booking_tracking_number = serializers.CharField(source="booking.tracking_number", read_only=True)
    package_title = serializers.CharField(source="booking.package.title", read_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=True)
    currency = serializers.SerializerMethodField()

    class Meta:
        model = BookingPayment
        fields = [
            "id",
            "booking_tracking_number",
            "package_title",
            "amount",
            "currency",
            "gateway",
            "status",
            "checkout_url",
            "failure_reason",
            "authorized_at",
            "created_at",
        ]

    def get_currency(self, obj):
        """Ensures consistent upper-casing for ISO currency symbols."""
        return obj.currency.upper() if obj.currency else "USD"