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
from .serializers import AdminPaymentListSerializer
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
from .serializers import SenderPaymentHistorySerializer
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

import decimal
from .serializers import AdminPaymentStatsSerializer
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
                    {"success": False, "message": "Plan is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ---------------------------
            # 1. VALIDATE PLAN
            # ---------------------------
            try:
                plan = Plan.objects.get(id=plan_id, is_active=True)
            except Plan.DoesNotExist:
                return Response(
                    {"success": False, "message": "Invalid or inactive plan."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not plan.stripe_price_id:
                return Response(
                    {"success": False, "message": "This plan is not configured for payments."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ---------------------------
            # 2. PREVENT DUPLICATE SUBSCRIPTIONS
            # ---------------------------
            active_subscription = getattr(request.user, "subscription", None)
            if active_subscription and getattr(active_subscription, "is_current", False):
                return Response(
                    {"success": False, "message": "You already have an active subscription."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ---------------------------
            # 3. VERIFY ACTUAL STRIPE PRICE AMOUNT (Fixes Amount Mismatch)
            # ---------------------------
            try:
                stripe_price = stripe.Price.retrieve(plan.stripe_price_id)
                # Convert Stripe unit_amount (cents) to Decimal dollars
                actual_price_amount = decimal.Decimal(stripe_price.unit_amount) / decimal.Decimal("100")
            except stripe.error.StripeError as e:
                return Response(
                    {"success": False, "message": f"Could not verify price on Stripe: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ---------------------------
            # 4. CREATE PENDING PAYMENT IN DB
            # ---------------------------
            # Sync DB payment amount to actual_price_amount fetched from Stripe
            payment = Payment.objects.create(
                user=request.user,
                plan=plan,
                amount=actual_price_amount,  # Guaranteed to match Stripe's price
                currency=plan.currency or stripe_price.currency.upper(),
                status=PaymentStatus.PENDING,
            )

            # ---------------------------
            # 5. REUSE OR CREATE STRIPE CUSTOMER
            # ---------------------------
            customer_id = getattr(request.user, "stripe_customer_id", None)
            session_kwargs = {
                "payment_method_types": ["card"],
                "mode": "subscription",
                "line_items": [{"price": plan.stripe_price_id, "quantity": 1}],
                "metadata": {
                    "payment_type": "subscription",
                    "payment_id": str(payment.id),
                    "booking_payment_id": str(payment.id),  # Unified key for webhook backwards-compatibility
                    "user_id": str(request.user.id),
                    "plan_id": str(plan.id),
                },
                "success_url": f"{settings.FRONTEND_URL}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{settings.FRONTEND_URL}/payments/failure",
            }

            if customer_id:
                session_kwargs["customer"] = customer_id
            else:
                session_kwargs["customer_email"] = request.user.email

            # ---------------------------
            # 6. CREATE CHECKOUT SESSION (Outside DB atomic lock)
            # ---------------------------
            checkout_session = stripe.checkout.Session.create(**session_kwargs)

            # Save session details back to payment record
            payment.stripe_checkout_session_id = checkout_session.id
            if hasattr(payment, "checkout_url"):
                payment.checkout_url = checkout_session.url
            payment.save(update_fields=["stripe_checkout_session_id"] + (["checkout_url"] if hasattr(payment, "checkout_url") else []))

            return Response(
                {
                    "success": True,
                    "message": "Checkout session created successfully.",
                    "checkout_url": checkout_session.url,
                    "session_id": checkout_session.id,
                },
                status=status.HTTP_201_CREATED,
            )

        except stripe.error.StripeError as e:
            return Response(
                {
                    "success": False,
                    "message": "Stripe error occurred.",
                    "error": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Something went wrong while creating checkout session.",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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



from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from apps.payment.models import (
    BookingPayment,
    BookingPaymentStatus,
)
from .serializers import AdminPaymentStatsSerializer


class AdminPaymentDashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):

        total_transactions = BookingPayment.objects.count()

        escrow_balance = (
            BookingPayment.objects.filter(
                status=BookingPaymentStatus.AUTHORIZED
            ).aggregate(
                total=Coalesce(
                    Sum("amount"),
                    Decimal("0.00"),
                )
            )["total"]
        )

        pending_escrow = escrow_balance

        released_escrow = (
            BookingPayment.objects.filter(
                status=BookingPaymentStatus.CAPTURED
            ).aggregate(
                total=Coalesce(
                    Sum("amount"),
                    Decimal("0.00"),
                )
            )["total"]
        )

        refund_amount = (
            BookingPayment.objects.filter(
                status=BookingPaymentStatus.REFUNDED
            ).aggregate(
                total=Coalesce(
                    Sum("amount"),
                    Decimal("0.00"),
                )
            )["total"]
        )

        platform_revenue = (
            BookingPayment.objects.filter(
                status=BookingPaymentStatus.CAPTURED
            ).aggregate(
                total=Coalesce(
                    Sum("platform_fee"),
                    Decimal("0.00"),
                )
            )["total"]
        )

        serializer = AdminPaymentStatsSerializer(
            {
                "total_transactions": total_transactions,
                "escrow_balance": escrow_balance,
                "pending_escrow": pending_escrow,
                "released_escrow": released_escrow,
                "refund_amount": refund_amount,
                "platform_revenue": platform_revenue,
            }
        )

        return Response(
            {
                "message": "Payment dashboard statistics fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )





class AdminPaymentListView(generics.ListAPIView):

    permission_classes = [IsAdminUser]
    serializer_class = AdminPaymentListSerializer

    def get_queryset(self):

        queryset = (
            BookingPayment.objects.select_related(
                "booking",
                "payer",
                "payee",
            )
            .order_by("-created_at")
        )

        # ----------------------------
        # Search
        # ----------------------------
        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(id__icontains=search)
                | Q(booking__id__icontains=search)
                | Q(payer__email__icontains=search)
                | Q(payee__email__icontains=search)
                | Q(transaction_id__icontains=search)
            )

        # ----------------------------
        # Payment Status Filter
        # ----------------------------
        status_filter = self.request.query_params.get("status")

        if status_filter:
            status_filter = status_filter.upper()

            valid_statuses = [
                choice[0]
                for choice in BookingPaymentStatus.choices
            ]

            if status_filter in valid_statuses:
                queryset = queryset.filter(
                    status=status_filter
                )

        return queryset

    

from apps.wallets.models import StripeConnectedAccount

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def stripe_connect_success_view(request):
    """
    Callback endpoint triggered when a user returns from Stripe onboarding.
    Queries Stripe to sync account verification statuses in real-time.
    """
    # 1 & 2. Rely strictly on query params since Stripe redirects drop JWT headers
    user_id = request.GET.get("user_id")
    if not user_id:
        return HttpResponse(
            "<h3>Invalid Request</h3><p>User identifier is missing.</p>", 
            status=400
        )

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return HttpResponse(
            "<h3>User Not Found</h3><p>No account matched the provided user ID.</p>", 
            status=404
        )

    # 3. Clean relation lookup using model class exception
    try:
        stripe_account_profile = StripeConnectedAccount.objects.get(user=user)
    except StripeConnectedAccount.DoesNotExist:
        return HttpResponse(
            "<h3>No Stripe Account Linked</h3><p>No Stripe Connect record exists for this user profile.</p>", 
            status=400
        )

    stripe_account_id = stripe_account_profile.stripe_account_id

    try:
        # 1. Retrieve real-time data directly from Stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        account = stripe.Account.retrieve(stripe_account_id)

        # 5. Strict Stripe status check requiring all three criteria
        is_fully_verified = (
            account.details_submitted
            and account.charges_enabled
            and account.payouts_enabled
        )

        # 4. Update ALL fields in an atomic transaction block
        with transaction.atomic():
            profile = StripeConnectedAccount.objects.select_for_update().get(id=stripe_account_profile.id)
            
            profile.payouts_enabled = account.payouts_enabled
            profile.charges_enabled = account.charges_enabled
            profile.details_submitted = account.details_submitted
            profile.country = account.country
            profile.default_currency = account.default_currency
            profile.account_status = "ACTIVE" if is_fully_verified else "PENDING"
            
            profile.save(update_fields=[
                "payouts_enabled",
                "charges_enabled",
                "details_submitted",
                "country",
                "default_currency",
                "account_status",
            ])

        # Render response feedback
        if is_fully_verified:
            status_title = "✓ Connection Successful!"
            status_color = "#00d68f"
            status_desc = "Your Stripe Connected Account is fully verified, active, and configured for secure balance withdrawals."
        else:
            status_title = "⚠ Onboarding Incomplete"
            status_color = "#e67e22"
            status_desc = "Your account link was registered, but Stripe requires more identification documentation before payouts can be unlocked."

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
                .status-tag {{ font-weight: bold; float: right; color: {"#00a870" if is_fully_verified else "#e67e22"}; }}
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
                    <tr><td>Account Status</td><td><span class="status-tag">{profile.account_status}</span></td></tr>
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


from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from apps.wallets.models import StripeConnectedAccount
from apps.payment.providers.stripe_connect import StripeConnectProvider


@api_view(["GET"])
@permission_classes([AllowAny])
def stripe_connect_refresh_view(request):
    user_id = request.GET.get("user_id")

    if not user_id:
        return HttpResponse("Missing user_id", status=400)

    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
        stripe_account = StripeConnectedAccount.objects.get(user=user)
    except (User.DoesNotExist, StripeConnectedAccount.DoesNotExist):
        return HttpResponse("Invalid user", status=404)

    onboarding_url = StripeConnectProvider.create_account_link(
        stripe_account.stripe_account_id,
        user,
    )

    return redirect(onboarding_url)





class SenderPaymentHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SenderPaymentHistorySerializer

    def get_queryset(self):
        return (
            WalletTransaction.objects.select_related(
                "wallet",
                "booking",
                "booking__package",
            )
            .filter(wallet__user=self.request.user)
            .exclude(type="DEPOSIT")  # optional
            .order_by("-created_at")
        )