from django.shortcuts import render

# Create your views here.
from decimal import Decimal
from django.db.models import Avg, Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from apps.trips.models import Trip, TripStatus
from apps.bookings.models import Booking, BookingStatus
from apps.reviews.models import Review
from .serializers import TravelerDashboardStatsSerializer



class TravelerDashboardStatsView(APIView):
    """
    API View providing real-time metrics for the logged-in Traveler.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # 1. Available Balance ($)
        wallet = getattr(user, "wallet", None)
        available_balance = Decimal("0.00")
        if wallet:
            available_balance = getattr(
                wallet,
                "balance",
                getattr(wallet, "available_balance", getattr(wallet, "amount", Decimal("0.00"))),
            )

        # 2. Active Deliveries (Packages currently being handled by traveler)
        active_deliveries = Booking.objects.filter(
            traveler=user,
            status__in=[
                BookingStatus.CONFIRMED,
                BookingStatus.PICKED_UP,
                BookingStatus.IN_TRANSIT,
            ],
            is_active=True,
        ).count()

        # 3. Active Trips (Includes PLANNED & ACTIVE trips that are active)
        # Includes trips where status is PLANNED or ACTIVE
        active_trips = Trip.objects.filter(
            traveler=user,
            is_active=True,
            status__in=[TripStatus.PLANNED, TripStatus.ACTIVE, "PLANNED", "ACTIVE"],
        ).count()

        # 4. Pending Requests (Incoming booking requests needing traveler approval)
        pending_requests = Booking.objects.filter(
            traveler=user,
            status=BookingStatus.PENDING,
            is_active=True,
        ).count()

        # 5. Rating (Average score from reviews received as a traveler)
        rating_agg = Review.objects.filter(traveler=user).aggregate(avg_rating=Avg("rating"))
        rating = round(float(rating_agg["avg_rating"] or 0.0), 2)

        # 6. Completed Deliveries
        completed_deliveries = Booking.objects.filter(
            traveler=user,
            status=BookingStatus.COMPLETED,
        ).count()

        # 7. Pending Earnings ($)
        pending_earnings_statuses = [
            BookingStatus.TRAVELER_ACCEPTED,
            BookingStatus.PAYMENT_PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.PICKED_UP,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED,
        ]
        pending_earnings_agg = Booking.objects.filter(
            traveler=user,
            status__in=pending_earnings_statuses,
            is_active=True,
        ).aggregate(total=Sum("agreed_reward"))
        pending_earnings = pending_earnings_agg["total"] or Decimal("0.00")

        # 8. Lifetime Earnings ($)
        lifetime_earnings_agg = Booking.objects.filter(
            traveler=user,
            status=BookingStatus.COMPLETED,
        ).aggregate(total=Sum("agreed_reward"))
        lifetime_earnings = lifetime_earnings_agg["total"] or Decimal("0.00")

        # Prepare Payload
        data = {
            "available_balance": available_balance,
            "active_deliveries": active_deliveries,
            "active_trips": active_trips,
            "pending_requests": pending_requests,
            "rating": rating,
            "completed_deliveries": completed_deliveries,
            "pending_earnings": pending_earnings,
            "lifetime_earnings": lifetime_earnings,
        }

        serializer = TravelerDashboardStatsSerializer(data)

        return Response(
            {
                "success": True,
                "message": "Traveler dashboard metrics calculated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )