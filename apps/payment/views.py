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
from .serializers import BookingPaymentHistorySerializer
from apps.notifications.models import Notification, NotificationType 
from django.http import HttpResponse

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.db import transaction
from .serializers import InitiateBookingPaymentSerializer
from .services import BookingPaymentService,SubscriptionWebhookService
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





from apps.notifications.services import create_bulk_notifications



from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from apps.wallets.models import Wallet, WithdrawalRequest, WalletTransaction

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
    event_data = event["data"]["object"].to_dict()

    try:
        # =====================================================
        # CHECKOUT SESSION COMPLETED
        # =====================================================
        if event_type == "checkout.session.completed":
            metadata = event_data.get("metadata", {}) or {}
            payment_type = metadata.get("payment_type")

            if payment_type == "booking":
                BookingPaymentService.process_webhook(event, raw_json=request.data)
            elif payment_type == "subscription":
                SubscriptionWebhookService.process(event)
            else:
                logger.warning("Unknown payment_type received: %s", payment_type)

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
            BookingPaymentService.process_webhook(event, raw_json=request.data)

        # =====================================================
        # CONNECT WITHDRAWAL PAYOUT EVENTS (🔗 STEP 7 ENUM UPDATED)
        # =====================================================
        elif event_type in [
            "payout.paid",
            "payout.failed",
            "payout.canceled"
        ]:
            payout_id = event_data.get("id")
            
            with transaction.atomic():
                try:
                    # Match the unique payout ID tracked on your WithdrawalRequest model
                    withdrawal = WithdrawalRequest.objects.select_for_update().get(stripe_payout_id=payout_id)
                except WithdrawalRequest.DoesNotExist:
                    logger.warning("Withdrawal request record not found for payout: %s", payout_id)
                    return HttpResponse(status=status.HTTP_200_OK)

                wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
                user = wallet.user

                # 🟢 STRIPE CONFIRMS SUCCESS
                if event_type == "payout.paid":
                    if withdrawal.status != WithdrawalRequest.WithdrawalStatus.COMPLETED:
                        withdrawal.status = WithdrawalRequest.WithdrawalStatus.COMPLETED
                        withdrawal.completed_at = timezone.now()
                        withdrawal.save(update_fields=["status", "completed_at"])

                        # Update total payout amounts
                        wallet.total_withdrawn += withdrawal.amount
                        wallet.save(update_fields=["total_withdrawn"])

                        # Create the historical withdrawal ledger record using explicit Model Enums
                        WalletTransaction.objects.create(
                            wallet=wallet,
                            type=WalletTransaction.TransactionType.WITHDRAWAL,
                            amount=-withdrawal.amount,
                            status=WalletTransaction.TransactionStatus.COMPLETED,
                            reference=withdrawal.stripe_payout_id,
                            description=f"Withdrawal settled safely to bank account profile."
                        )
                        
                        # 🔔 Trigger Notifications and Email delivery pipelines on successful commit
                        transaction.on_commit(lambda: create_bulk_notifications(
                            users=[user],
                            title="Withdrawal Completed",
                            message=f"Success! Your payout of ${withdrawal.amount} has cleared and settled in your bank account."
                        ))
                        
                        try:
                            from apps.notifications.utils.email import send_withdrawal_completed_email
                            transaction.on_commit(lambda: send_withdrawal_completed_email(user, withdrawal))
                        except ImportError:
                            logger.warning("send_withdrawal_completed_email function missing or not found.")

                # 🔴 STRIPE CONFIRMS BANK REJECTION / CANCELLATION
                elif event_type in ["payout.failed", "payout.canceled"]:
                    if withdrawal.status != WithdrawalRequest.WithdrawalStatus.FAILED:
                        withdrawal.status = WithdrawalRequest.WithdrawalStatus.FAILED
                        withdrawal.rejection_reason = event_data.get("failure_message") or "Stripe bank clearance failure."
                        withdrawal.save(update_fields=["status", "rejection_reason"])

                        # Revert frozen liquidity back to user liquid available balance
                        balance_before = wallet.available_balance
                        wallet.available_balance += withdrawal.amount
                        wallet.save(update_fields=["available_balance"])

                        # Create a reversal logging trace using your exact Model Enums
                        WalletTransaction.objects.create(
                            wallet=wallet,
                            type=WalletTransaction.TransactionType.REFUND,
                            amount=withdrawal.amount,
                            status=WalletTransaction.TransactionStatus.COMPLETED,
                            reference=payout_id,
                            description=f"Bank Clearance Failed: {withdrawal.rejection_reason}. Funds returned to account balance."
                        )

                        # 🔔 Notify Failed Flow
                        transaction.on_commit(lambda: create_bulk_notifications(
                            users=[user],
                            title="Withdrawal Failed",
                            message=f"Your bank transfer of ${withdrawal.amount} could not clear. Funds have been returned to your wallet balance."
                        ))

        else:
            logger.info("Ignoring unsupported Stripe event: %s", event_type)

    except Exception:
        logger.exception("Stripe webhook processing failed for event: %s", event_type)
        return HttpResponse(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return HttpResponse(status=status.HTTP_200_OK)



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

from django.db.models import Q

class BookingPaymentHistoryListView(generics.ListAPIView):
    """
    Production API Endpoint to retrieve paginated, historical escrow booking payments 
    initiated by (or released to) the authenticated user.
    """
    serializer_class = BookingPaymentHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        logger.info("User %s requested their escrow booking payment history.", user.id)

        # 🟢 FIX: Allow both Senders (who paid) and Travelers (who earned) to see the history
        return (
            BookingPayment.objects
            .filter(
                Q(booking__sender=user) | Q(booking__traveler=user)
            )
            .select_related(
                "booking", 
                "booking__package"
            )
            .order_by("-created_at")
        )





# adjusting below based on your architecture:
@api_view(['GET'])                  # 👈 Tells Django this is a DRF-managed GET view
@permission_classes([AllowAny])    # 👈 Bypasses global authentication requirements
def stripe_connect_success_view(request):
    """
    Callback endpoint triggered when a user returns from Stripe onboarding.
    Queries Stripe to sync account verification statuses in real-time.
    """
    user = request.user
    
    # Fallback if testing directly in browser session context without API token auth header
    if not user or not user.is_authenticated:
        user_id = request.GET.get("user_id")
        User = get_user_model()
        user = User.objects.filter(id=user_id).first() if user_id else None
        
    if not user:
        return HttpResponse(
            "<h3>Authentication Context Missing</h3><p>Please include ?user_id=<id> in your testing browser URL to simulate auth context.</p>", 
            status=401
        )

    try:
        # Explicit lookup to safely verify if user has an associated stripe account profile
        stripe_account_profile = user.stripe_account 
    except getattr(user.__class__, 'stripe_account').RelatedObjectDoesNotExist:
        return HttpResponse("<h3>Error</h3><p>No Stripe Account profile linked to this user.</p>", status=400)
    except Exception as e:
        return HttpResponse(f"<h3>Profile Error</h3><p>{str(e)}</p>", status=400)

    stripe_account_id = stripe_account_profile.stripe_account_id

    try:
        # 1. Retrieve current data directly from Stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        account = stripe.Account.retrieve(stripe_account_id)

        # 2. Update database flags in an atomic transaction blocks
        with transaction.atomic():
            profile = type(stripe_account_profile).objects.select_for_update().get(id=stripe_account_profile.id)
            profile.payouts_enabled = account.payouts_enabled
            profile.charges_enabled = account.charges_enabled
            profile.details_submitted = account.details_submitted
            profile.save(update_fields=["payouts_enabled", "charges_enabled", "details_submitted"])

        # 3. Dynamic Visual Response based on their actual state
        if profile.payouts_enabled and profile.details_submitted:
            status_title = "✓ Connection Successful!"
            status_color = "#00d68f"
            status_desc = "Your Stripe Connected Account is fully verified, active, and configured for secure balance withdrawals."
        else:
            status_title = "⚠ Onboarding Incomplete"
            status_color = "#e67e22"
            status_desc = "Your account link was registered, but Stripe requires more identification documentation before your payouts can be unlocked."

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Onboarding Status</title>
            <style>
                body {{ font-family: system-ui, -apple-system, sans-serif; text-align: center; background: #f4f6f8; padding: 50px; color: #202124; }}
                .card {{ max-width: 450px; background: white; padding: 40px; border-radius: 12px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
                h1 {{ color: {status_color}; margin-bottom: 8px; }}
                p {{ color: #5f6368; line-height: 1.5; }}
                .badge-table {{ width: 100%; margin-top: 20px; border-collapse: collapse; }}
                .badge-table td {{ padding: 8px 12px; font-size: 14px; text-align: left; border-bottom: 1px solid #f0f2f5; }}
                .status-tag {{ font-weight: bold; float: right; color: {"#00a870" if profile.payouts_enabled else "#e67e22"}; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>{status_title}</h1>
                <p>{status_desc}</p>
                <table class="badge-table">
                    <tr><td>Details Submitted</td><td><span class="status-tag">{"True" if profile.details_submitted else "False"}</span></td></tr>
                    <tr><td>Charges Enabled</td><td><span class="status-tag">{"True" if profile.charges_enabled else "False"}</span></td></tr>
                    <tr><td>Payouts Enabled</td><td><span class="status-tag">{"True" if profile.payouts_enabled else "False"}</span></td></tr>
                </table>
                <p style="font-size: 13px; color: #70757a; margin-top: 24px;">You can safely close this browser tab or return to your application profile window.</p>
            </div>
        </body>
        </html>
        """
        return HttpResponse(html_content, content_type="text/html")

    except Exception as e:
        logger.exception("Failed to verify return state with Stripe Connect.")
        return HttpResponse(f"<h3>Verification Error</h3><p>{str(e)}</p>", status=500)
    

def stripe_connect_refresh_view(request):
    """Fallback expired onboarding renewal page."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Session Expired</title>
        <style>
            body { font-family: system-ui, sans-serif; text-align: center; background: #f4f6f8; padding: 50px; color: #202124; }
            .card { max-width: 450px; background: white; padding: 40px; border-radius: 12px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
            h1 { color: #e67e22; margin-bottom: 8px; }
            p { color: #5f6368; line-height: 1.5; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Session Timeout</h1>
            <p>Your secure verification setup link with Stripe has expired or been used already.</p>
            <p>Please return to your wallet dashboard menu and click <strong>"Connect Bank"</strong> again to generate a new onboarding link.</p>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_content, content_type="text/html")