from django.shortcuts import render

# Create your views here.
from django.db.models import Count
from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from itertools import chain

from django.utils import timezone
from django.utils.timesince import timesince

from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from apps.bookings.models import Booking, BookingStatus
from apps.matching.models import Match
from apps.wallets.models import WithdrawalRequest
from apps.profiles.models import Profile
from apps.disputes.models import Dispute
from django.utils import timezone
from django.utils.timesince import timesince

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from apps.matching.models import Match
from apps.bookings.models import Booking, BookingStatus
from apps.wallets.models import WithdrawalRequest

from apps.kyc.models import KYC, KYCStatus

from .serializers import AdminRecentActivitySerializer

from .serializers import AdminRecentActivitySerializer

from apps.bookings.models import Booking, BookingStatus


class TopRoutesAPIView(generics.GenericAPIView):
    """
    Returns the top 5 most used delivery routes based on completed bookings.
    """

    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):

        routes = (
            Booking.objects.filter(status=BookingStatus.COMPLETED)
            .values(
                "package__pickup_country",
                "package__pickup_city",
                "package__destination_country",
                "package__destination_city",
            )
            .annotate(
                total_deliveries=Count("id")
            )
            .order_by("-total_deliveries")[:5]
        )

        return Response(
            {
                "success": True,
                "message": "Top 5 most used delivery routes.",
                "results": routes,
            }
        )




class AdminRecentActivityView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        activities = []
        now = timezone.now()

        # ==========================================================
        # Package Matched
        # ==========================================================
        matches = Match.objects.select_related("package", "trip").order_by(
            "-created_at"
        )[:10]

        for match in matches:
            activities.append(
                {
                    "type": "MATCH",
                    "title": "Package matched successfully",
                    "description": (
                        f"Package #{match.package.id} matched with Trip #{match.trip.id}."
                    ),
                    "created_at": match.created_at,
                }
            )

        # ==========================================================
        # Booking Confirmed
        # ==========================================================
        bookings = (
            Booking.objects.select_related("package")
            .filter(status=BookingStatus.CONFIRMED)
            .order_by("-confirmed_at")[:10]
        )

        for booking in bookings:
            activities.append(
                {
                    "type": "BOOKING",
                    "title": "Booking confirmed",
                    "description": (
                        f"Booking #{booking.tracking_number} has been confirmed."
                    ),
                    "created_at": booking.confirmed_at or booking.created_at,
                }
            )

        # ==========================================================
        # Delivery Completed
        # ==========================================================
        deliveries = (
            Booking.objects.select_related(
                "package",
                "traveler",
                "traveler__profile",
            )
            .filter(status=BookingStatus.COMPLETED)
            .order_by("-completed_at")[:10]
        )

        for booking in deliveries:
            if hasattr(booking.traveler, "profile") and booking.traveler.profile:
                traveler_name = (
                    f"{booking.traveler.profile.first_name} "
                    f"{booking.traveler.profile.last_name}"
                ).strip()
            else:
                traveler_name = booking.traveler.email

            activities.append(
                {
                    "type": "DELIVERY",
                    "title": "Delivery completed",
                    "description": (
                        f"{traveler_name} delivered Booking #{booking.tracking_number}."
                    ),
                    "created_at": booking.completed_at or booking.created_at,
                }
            )

        # ==========================================================
        # Payment Released
        # ==========================================================
        withdrawals = (
            WithdrawalRequest.objects.select_related("wallet__user")
            .filter(status="COMPLETED")
            .order_by("-updated_at")[:10]
        )

        for withdrawal in withdrawals:
            activities.append(
                {
                    "type": "PAYMENT",
                    "title": "Payment released",
                    "description": (
                        f"${withdrawal.amount} transferred to Traveler Wallet."
                    ),
                    "created_at": withdrawal.updated_at,
                }
            )

        # ==========================================================
        # KYC Approved
        # ==========================================================
        kycs = (
            KYC.objects.select_related("user", "user__profile")
            .filter(status=KYCStatus.APPROVED)
            .order_by("-verified_at")[:10]
        )

        for kyc in kycs:
            if hasattr(kyc.user, "profile") and kyc.user.profile:
                full_name = (
                    f"{kyc.user.profile.first_name} "
                    f"{kyc.user.profile.last_name}"
                ).strip()

                if not full_name:
                    full_name = kyc.user.email
            else:
                full_name = kyc.user.email

            activities.append(
                {
                    "type": "KYC",
                    "title": "KYC Approved",
                    "description": (
                        f"{full_name}'s identity verification completed."
                    ),
                    "created_at": kyc.verified_at
                    or kyc.updated_at
                    or kyc.created_at,
                }
            )

        # ==========================================================
        # Disputes
        # ==========================================================
        disputes = Dispute.objects.select_related("booking").order_by(
            "-created_at"
        )[:10]

        for dispute in disputes:
            activities.append(
                {
                    "type": "DISPUTE",
                    "title": "Dispute Opened",
                    "description": (
                        f"Dispute #{dispute.id} created for Booking #{dispute.booking.tracking_number}."
                    ),
                    "created_at": dispute.created_at,
                }
            )

        # ==========================================================
        # Sort Latest First
        # ==========================================================
        activities = sorted(
            activities,
            key=lambda x: x["created_at"] or now,
            reverse=True,
        )[:10]

        # ==========================================================
        # Human Time (Safe Fallback)
        # ==========================================================
        for activity in activities:
            timestamp = activity["created_at"] or now
            activity["time"] = f"{timesince(timestamp, now)} ago"

        serializer = AdminRecentActivitySerializer(
            activities,
            many=True,
        )

        return Response(
            {
                "message": "Recent activities fetched successfully.",
                "count": len(serializer.data),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from apps.accounts.models import User
from apps.packages.models import Package
from apps.bookings.models import Booking, BookingStatus
from apps.wallets.models import WalletTransaction
from apps.kyc.models import KYC, KYCStatus
from apps.disputes.models import Dispute
from django.db.models import Sum

from .serializers import AdminDashboardStatsSerializer


class AdminDashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):

        total_users = User.objects.count()

        total_packages = Package.objects.count()

        total_bookings = Booking.objects.count()

        active_deliveries = Booking.objects.filter(
            status__in=[
                BookingStatus.PICKED_UP,
                BookingStatus.IN_TRANSIT,
            ]
        ).count()

        completed_deliveries = Booking.objects.filter(
            status=BookingStatus.COMPLETED
        ).count()

        pending_kyc = KYC.objects.filter(
            status__in=[
                KYCStatus.PENDING,
                KYCStatus.UNDER_REVIEW,
            ]
        ).count()

        open_disputes = Dispute.objects.exclude(
            status="RESOLVED"
        ).count()



        platform_revenue = (
            Booking.objects.filter(
                status=BookingStatus.COMPLETED
            ).aggregate(
                total=Sum("agreed_reward")
            )["total"]
            or Decimal("0.00")
        )

        data = {
            "total_users": total_users,
            "total_packages": total_packages,
            "total_bookings": total_bookings,
            "platform_revenue": platform_revenue,
            "active_deliveries": active_deliveries,
            "completed_deliveries": completed_deliveries,
            "pending_kyc": pending_kyc,
            "open_disputes": open_disputes,
        }

        serializer = AdminDashboardStatsSerializer(data)

        return Response(
            {
                "message": "Dashboard statistics fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )