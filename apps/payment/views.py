from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.bookings.models import Booking, BookingStatus
from apps.payment.models import Payment
from apps.payment.serializers import PaymentSerializer
import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from datetime import timedelta
from apps.payment.models import Payment, PaymentStatus
from apps.subscriptions.models import Subscription, SubscriptionStatus, Plan
from django.contrib.auth import get_user_model
import traceback
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from apps.accounts.models import User
import logging
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError
import json
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAdminUser  
from .models import BookingPayment, BookingPaymentLog
from .services import BookingPaymentService
import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from .serializers import BookingPaymentHistorySerializer


# 🟢 Import your notification model structures here
from apps.notifications.models import Notification, NotificationType 

from .serializers import InitiateBookingPaymentSerializer
from .services import BookingPaymentService

logger = logging.getLogger(__name__)


User = get_user_model()

stripe.api_key = settings.STRIPE_SECRET_KEY




class CreateCheckoutSessionView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        try:
            plan_id = request.data.get("plan")

            if not plan_id:
                return Response(
                    {
                        "success": False,
                        "message": "Plan is required."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ---------------------------
            # VALIDATE PLAN
            # ---------------------------
            try:
                plan = Plan.objects.get(id=plan_id, is_active=True)
            except Plan.DoesNotExist:
                return Response(
                    {
                        "success": False,
                        "message": "Invalid or inactive plan."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            # ---------------------------
            # CHECK STRIPE PRICE
            # ---------------------------
            if not plan.stripe_price_id:
                return Response(
                    {
                        "success": False,
                        "message": "This plan is not configured for payments."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ---------------------------
            # OPTIONAL: Prevent duplicate active subscription
            # ---------------------------
            active_subscription = getattr(request.user, "subscription", None)

            if active_subscription and active_subscription.is_current:
                return Response(
                    {
                        "success": False,
                        "message": "You already have an active subscription."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            with transaction.atomic():

                # ---------------------------
                # CREATE PAYMENT (PENDING)
                # ---------------------------
                payment = Payment.objects.create(
                    user=request.user,
                    plan=plan,
                    amount=plan.price,
                    currency=plan.currency,
                    status=PaymentStatus.PENDING,
                )

                # ---------------------------
                # CREATE STRIPE CHECKOUT SESSION
                # ---------------------------
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="subscription",
                    customer_email=request.user.email,
                    line_items=[
                        {
                            "price": plan.stripe_price_id,
                            "quantity": 1,
                        }
                    ],
                    metadata={
                        "payment_type": "subscription",
                        "payment_id": str(payment.id),
                        "user_id": str(request.user.id),
                        "plan_id": str(plan.id),
                    },
                    success_url=f"{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{settings.FRONTEND_URL}/payment/cancel",
                )

                # ---------------------------
                # UPDATE PAYMENT WITH SESSION ID
                # ---------------------------
                payment.stripe_checkout_session_id = checkout_session.id
                payment.save()

            return Response(
                {
                    "success": True,
                    "message": "Checkout session created successfully.",
                    "checkout_url": checkout_session.url,
                    "session_id": checkout_session.id,
                },
                status=status.HTTP_201_CREATED
            )

        except stripe.error.StripeError as e:
            return Response(
                {
                    "success": False,
                    "message": "Stripe error occurred.",
                    "error": str(e)
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Something went wrong while creating checkout session.",
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# new webhook view for booking payments

import stripe
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from .services import BookingPaymentService,SubscriptionWebhookService


logger = logging.getLogger(__name__)




@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def stripe_webhook(request):

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    # -----------------------------------------------------
    # Verify Stripe Signature
    # -----------------------------------------------------

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=endpoint_secret,
        )

    except ValueError:
        logger.exception("Invalid Stripe webhook payload.")
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

    except stripe.error.SignatureVerificationError:
        logger.exception("Invalid Stripe webhook signature.")
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

    event_type = event["type"]
    event_data = event["data"]["object"]

    try:

        # =====================================================
        # CHECKOUT SESSION COMPLETED
        # =====================================================

        if event_type == "checkout.session.completed":

            metadata = event_data.get("metadata", {}) or {}
            payment_type = metadata.get("payment_type")

            if payment_type == "booking":

                BookingPaymentService.process_webhook(event)

            elif payment_type == "subscription":

                SubscriptionWebhookService.process(event)

            else:

                logger.warning(
                    "Unknown payment_type received: %s",
                    payment_type,
                )

        # =====================================================
        # SUBSCRIPTION EVENTS
        # =====================================================

        elif event_type in [
            "invoice.paid",
            "invoice.payment_failed",
        ]:

            SubscriptionWebhookService.process(event)

        # =====================================================
        # BOOKING PAYMENT EVENTS
        # =====================================================

        elif event_type in [
            "payment_intent.payment_failed",
            "charge.refunded",
            "checkout.session.expired",
        ]:

            BookingPaymentService.process_webhook(event)

        else:

            logger.info(
                "Ignoring unsupported Stripe event: %s",
                event_type,
            )

    except Exception:

        logger.exception(
            "Stripe webhook processing failed for event: %s",
            event_type,
        )

        return HttpResponse(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return HttpResponse(status=status.HTTP_200_OK)






class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

        if not sig_header:
            return Response(
                {
                    "success": False,
                    "message": "Missing Stripe signature.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )

        except ValueError:
            return Response(
                {
                    "success": False,
                    "message": "Invalid payload.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except stripe.error.SignatureVerificationError:
            return Response(
                {
                    "success": False,
                    "message": "Invalid Stripe signature.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event_type = event["type"]
            data = event["data"]["object"].to_dict()

            print(f"Webhook Event: {event_type}")

            # =====================================================
            # CHECKOUT COMPLETED
            # =====================================================
            if event_type == "checkout.session.completed":

                metadata = data.get("metadata", {})

                payment_id = metadata.get("payment_id")
                plan_id = metadata.get("plan_id")
                user_id = metadata.get("user_id")

                print("Metadata:", metadata)

                if not all([payment_id, plan_id, user_id]):
                    return Response(
                        {
                            "success": False,
                            "message": "Missing metadata.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                with transaction.atomic():

                    payment = (
                        Payment.objects
                        .select_for_update()
                        .get(id=payment_id)
                    )

                    # Prevent duplicate processing
                    if payment.status == PaymentStatus.SUCCEEDED:
                        return Response({"received": True})

                    user = User.objects.get(id=user_id)
                    plan = Plan.objects.get(id=plan_id)

                    # Update payment
                    payment.status = PaymentStatus.SUCCEEDED
                    payment.stripe_payment_intent_id = data.get(
                        "payment_intent"
                    )
                    payment.stripe_customer_id = data.get("customer")
                    payment.paid_at = timezone.now()
                    payment.save()

                    # Expire previous subscriptions
                    Subscription.objects.filter(
                        user=user,
                        is_current=True,
                    ).update(
                        is_current=False,
                        status=SubscriptionStatus.EXPIRED,
                    )

                    # Create new subscription
                    subscription = Subscription.objects.create(
                        user=user,
                        plan=plan,
                        status=SubscriptionStatus.ACTIVE,
                        started_at=timezone.now(),
                        expires_at=timezone.now()
                        + timedelta(days=plan.duration_days),
                        is_current=True,
                    )

                    print("Payment Updated:", payment.id)
                    print("Subscription Created:", subscription.id)

            # =====================================================
            # PAYMENT FAILED
            # =====================================================
            elif event_type == "invoice.payment_failed":

                payment_intent = data.get("payment_intent")

                Payment.objects.filter(
                    stripe_payment_intent_id=payment_intent
                ).update(
                    status=PaymentStatus.FAILED,
                    failure_reason="Stripe payment failed",
                )

                print("Payment Failed:", payment_intent)

            # =====================================================
            # INVOICE PAID (Backup)
            # =====================================================
            elif event_type == "invoice.paid":

                payment_intent = data.get("payment_intent")

                Payment.objects.filter(
                    stripe_payment_intent_id=payment_intent
                ).update(
                    status=PaymentStatus.SUCCEEDED,
                    paid_at=timezone.now(),
                )

                print("Invoice Paid:", payment_intent)

            # =====================================================
            # IGNORE OTHER EVENTS
            # =====================================================
            else:
                print(f"Ignoring event: {event_type}")

            return Response({"received": True}, status=status.HTTP_200_OK)

        except Payment.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Payment not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "User not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Plan.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Plan not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            traceback.print_exc()

            return Response(
                {
                    "success": False,
                    "message": "Webhook processing failed.",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



class PaymentHistoryView(generics.ListAPIView):

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Payment.objects.filter(user=self.request.user)
            .select_related("plan", "subscription")
            .order_by("-created_at")
        )



class PaymentDetailView(generics.RetrieveAPIView):

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return (
            Payment.objects.filter(user=self.request.user)
            .select_related("plan", "subscription")
        )




# create payment for biooking

class BookingPaymentInitiateView(generics.CreateAPIView):
    """
    API Endpoint to initiate a secure escrow checkout session for a specific booking.
    Returns a third-party checkout redirection link (Stripe/bKash/Nagad).
    """
    serializer_class = InitiateBookingPaymentSerializer
    permission_classes = [IsAuthenticated]

    def _get_client_ip(self, request):
        """Extracts the true client IP address behind proxies for security logging."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        
        # 🟢 Native framework exception handler execution
        serializer.is_valid(raise_exception=True)

        # 🟢 Extract cached object instances from validated_data dict context mapping 
        booking = serializer.validated_data["booking"]
        gateway = serializer.validated_data["gateway"]
        client_ip = self._get_client_ip(request)
        user_email = request.user.email  

        try:
            # Route transaction preparation directly to our secure Service Layer
            payment_record = BookingPaymentService.create_checkout(
                booking=booking,
                gateway=gateway,
                user_email=user_email,
                client_ip=client_ip
            )
            
            return Response(
                {
                    "success": True,
                    "message": "Payment checkout session successfully provisioned.",
                    "data": {
                        "payment_id": payment_record.id,
                        "gateway": payment_record.gateway,
                        "status": payment_record.status,
                        "checkout_url": payment_record.checkout_url,
                        "amount": payment_record.amount,
                        "currency": payment_record.currency
                    }
                },
                status=status.HTTP_201_CREATED,
            )
            
        except DjangoValidationError as e:
            # 🟢 Unified project response status fallback error payload mapping
            return Response(
                {
                    "success": False,
                    "message": "Transaction initialization rejected by core system engine.",
                    "errors": e.message if hasattr(e, "message") else str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
            
        except Exception as e:
            logger.critical(f"Critical error on checkout routing execution: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": "An unexpected system fault occurred while generating payment channels.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


from .models import BookingPayment, BookingPaymentLog, BookingPaymentStatus
# webhook for payment verification
@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    """
    Enterprise-grade Webhook Listener enforcing transaction idempotency, multi-event routing,
    global audit tracking, and cryptographic authenticity verification.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

        event = None

        # 1. Cryptographic Signature Verification (Anti-Spoofing)
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.error(f"Stripe Webhook signature verification rejected: {str(e)}")
            return HttpResponse(status=400)

        event_type = event["type"]

        # Convert StripeObject to a normal Python dict
        event_data = event["data"]["object"].to_dict()

        metadata = event_data.get("metadata", {})
        payment_id = metadata.get("booking_payment_id")


        # 4.  LOG EVERY WEBHOOK: Capture all incoming traffic immutably for debugging
        payment_instance = None
        if payment_id:
            try:
                payment_instance = BookingPayment.objects.get(id=payment_id)
            except BookingPayment.DoesNotExist:
                logger.warning(f"Webhook {event_type} contained an untrackable Payment ID: {payment_id}")

        BookingPaymentLog.objects.create(
            booking_payment=payment_instance,
            event_type=event_type,
            raw_payload=json.loads(payload.decode("utf-8")),
        )

        if not payment_instance:
            return HttpResponse(status=200)

        # 6. 🟢 WRAP WEBHOOK EXECUTION IN A DATABASE TRANSACTION BLOCK
        try:
            with transaction.atomic():
                # Acquire a row lock to prevent race conditions from concurrent duplicate deliveries
                payment = BookingPayment.objects.select_for_update().get(id=payment_instance.id)

                # 1. & 3. 🟢 MULTI-EVENT HANDLING & VALIDATION STATUS CHECKING
                
                # --- EVENT A: CHECKOUT SESSION COMPLETED ---
                if event_type == "checkout.session.completed":
                    # 3. 🟢 Verify payment status: explicitly check that it is actually "paid"
                    if event_data.get("payment_status") != "paid":
                        logger.warning(f"Session completed but payment status was unconfirmed: {event_data.get('payment_status')}")
                        return HttpResponse(status=200)

                    # 2. 🟢 Prevent duplicate webhook processing (Idempotency Guard)
                    if payment.status == BookingPaymentStatus.AUTHORIZED:
                        logger.info(f"Idempotency Triggered: Payment {payment.id} already authorized.")
                        return HttpResponse(status=200)

                    # Execute state progression and trip capacity adjustments
                    BookingPaymentService.verify_checkout(
                        payment=payment,
                        provider_session_id=event_data["id"],
                        final_transaction_id=event_data.get("payment_intent")
                    )

                    # Dispatch User Notifications
                    Notification.objects.create(
                        user=payment.payer,
                        title="Payment Secured in Escrow",
                        message=f"Your payment of {payment.amount} {payment.currency} for order #{payment.booking.tracking_number} is locked in escrow.",
                        notification_type=NotificationType.PAYMENT,
                        object_id=payment.booking.id,
                        action_url=f"/bookings/{payment.booking.id}/"
                    )
                    Notification.objects.create(
                        user=payment.payee,
                        title="Luggage Space Reserved",
                        message=f"The sender funded the escrow for order #{payment.booking.tracking_number}. Your reward balance is secured.",
                        notification_type=NotificationType.PAYMENT,
                        object_id=payment.booking.id,
                        action_url=f"/bookings/{payment.booking.id}/"
                    )

                # --- EVENT B: CHECKOUT SESSION EXPIRED ---
                elif event_type == "checkout.session.expired":
                    if payment.status in [BookingPaymentStatus.AUTHORIZED, BookingPaymentStatus.CAPTURED]:
                        return HttpResponse(status=200)  # Safeguard active payments
                        
                    BookingPaymentService.mark_failed(payment, reason="Stripe checkout redirection window expired.")
                    
                    Notification.objects.create(
                        user=payment.payer,
                        title="Payment Redirection Expired",
                        message=f"Checkout session timed out for order #{payment.booking.tracking_number}. Please try initiating payment again.",
                        notification_type=NotificationType.PAYMENT,
                        object_id=payment.booking.id,
                    )

                # --- EVENT C: PAYMENT INTENT FAILED ---
                elif event_type == "payment_intent.payment_failed":
                    last_error = event_data.get("last_payment_error", {})
                    error_msg = last_error.get("message", "Declined by issuing bank.")
                    
                    BookingPaymentService.mark_failed(payment, reason=f"Stripe Intent Failed: {error_msg}")
                    
                    Notification.objects.create(
                        user=payment.payer,
                        title="Escrow Deposit Declined",
                        message=f"Transaction processing failed for order #{payment.booking.tracking_number}: {error_msg}",
                        notification_type=NotificationType.PAYMENT,
                        object_id=payment.booking.id,
                    )

                # --- EVENT D: CHARGE REFUNDED ---
                elif event_type == "charge.refunded":
                    if payment.status == BookingPaymentStatus.REFUNDED:
                        return HttpResponse(status=200)

                    BookingPaymentService.refund(payment)
                    
                    Notification.objects.create(
                        user=payment.payer,
                        title="Funds Refunded Successfully",
                        message=f"Escrow settlement balance of {payment.amount} {payment.currency} has been returned to your original card issuer.",
                        notification_type=NotificationType.PAYMENT,
                        object_id=payment.booking.id,
                    )

        except Exception as e:
            logger.critical(f"Database error executing webhook updates: {str(e)}", exc_info=True)
            return HttpResponse(status=500)

        return HttpResponse(status=200)




# booking payment relase views

class BookingPaymentReleaseView(APIView):
    """
    System/Admin-only route to execute emergency manual escrow release capture overrides.
    """
    # 🟢 Change permission classes so ordinary authenticated users are rejected out-of-the-box
    permission_classes = [IsAdminUser]

    def post(self, request, booking_id, *args, **kwargs):
        try:
            with transaction.atomic():
                booking = Booking.objects.select_for_update().get(id=booking_id)
                
                if booking.status != BookingStatus.DELIVERED:
                    return Response(
                        {"success": False, "message": "Escrow funds cannot be released unless state is DELIVERED."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                payment = BookingPayment.objects.select_for_update().get(booking=booking)

                # 🟢 Trigger service execution: All updates, statuses, and notifications execute safely here
                BookingPaymentService.release(payment)

                return Response(
                    {
                        "success": True,
                        "message": "Escrow balance successfully released via administrative override operations.",
                        "current_status": BookingStatus.COMPLETED
                    },
                    status=status.HTTP_200_OK
                )

        except (Booking.DoesNotExist, BookingPayment.DoesNotExist):
            return Response({"success": False, "message": "Target database records not found."}, status=status.HTTP_404_NOT_FOUND)
        except DjangoValidationError as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.critical(f"Critical execution error: {str(e)}", exc_info=True)
            return Response({"success": False, "message": "Internal error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




logger = logging.getLogger(__name__)

class BookingPaymentHistoryListView(generics.ListAPIView):
    """
    Production API Endpoint to retrieve paginated, historical escrow booking payments 
    initiated by the authenticated user (sender).
    """
    serializer_class = BookingPaymentHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        logger.info("User %s requested their escrow booking payment history.", user.id)

        # Optimization: Fetch booking and nested package records in a single JOIN query
        return (
            BookingPayment.objects
            .filter(booking__sender=user)
            .select_related(
                "booking", 
                "booking__package"
            )
            .order_by("-created_at")
        )