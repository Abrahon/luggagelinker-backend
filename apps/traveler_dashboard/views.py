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
import calendar
from decimal import Decimal
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from django.utils import timezone
from django.contrib.humanize.templatetags.humanize import naturaltime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from apps.bookings.models import Booking, BookingStatus
from apps.matching.models import Match  
from apps.wallets.models import WalletTransaction, WithdrawalRequest
from .serializers import CompactActivitySerializer


from apps.bookings.models import Booking, BookingStatus
from .serializers import MonthlyEarningsChartSerializer



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






class TravelerMonthlyEarningsChartView(APIView):
    """
    Returns monthly aggregated earnings for a traveler for a specific year
    to render bar charts.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Get year from query params, default to current year
        current_year = timezone.now().year
        try:
            target_year = int(request.query_params.get("year", current_year))
        except ValueError:
            target_year = current_year

        # 1. Query completed bookings for the specified year
        # Uses completed_at timestamp (or updated_at if completed_at is null)
        monthly_query = (
            Booking.objects.filter(
                traveler=user,
                status=BookingStatus.COMPLETED,
                completed_at__year=target_year,
            )
            .annotate(month=TruncMonth("completed_at"))
            .values("month")
            .annotate(total_earnings=Sum("agreed_reward"))
            .order_by("month")
        )

        # 2. Map database results to a dictionary {month_number: earnings}
        earnings_by_month = {}
        for entry in monthly_query:
            if entry["month"]:
                month_num = entry["month"].month
                earnings_by_month[month_num] = entry["total_earnings"] or Decimal("0.00")

        # 3. Build a complete 12-month array (Jan to Dec) for front-end charts
        chart_data = []
        total_year_earnings = Decimal("0.00")

        for m in range(1, 13):
            month_earnings = earnings_by_month.get(m, Decimal("0.00"))
            total_year_earnings += month_earnings

            chart_data.append(
                {
                    "month": calendar.month_abbr[m],  # 'Jan', 'Feb', etc.
                    "month_number": m,
                    "year": target_year,
                    "earnings": month_earnings,
                }
            )

        payload = {
            "year": target_year,
            "total_year_earnings": total_year_earnings,
            "chart_data": chart_data,
        }

        serializer = MonthlyEarningsChartSerializer(payload)

        return Response(
            {
                "success": True,
                "message": f"Monthly earnings for {target_year} retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )



class TravelerRecentActivitiesView(APIView):
    """
    Returns a unified real-time feed of traveler activities using models:
    - Match (ROUTE_MATCH)
    - Booking (BOOKING_REQUEST, BOOKING_ACCEPTED, etc.)
    - WalletTransaction (ESCROW_RELEASE, REFUND)
    - WithdrawalRequest (WITHDRAWAL_REQUESTED, WITHDRAWAL_COMPLETED)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        limit = int(request.query_params.get("limit", 10))

        activities = []

        # -------------------------------------------------------------
        # 1. ROUTE MATCHES
        # -------------------------------------------------------------
        matches = Match.objects.filter(
            trip__traveler=user,
            is_active=True
        ).select_related("trip").order_by("-created_at")[:limit]

        trip_matches = {}
        for m in matches:
            trip_id = m.trip.id
            if trip_id not in trip_matches:
                trip_matches[trip_id] = {
                    "trip": m.trip,
                    "count": 0,
                    "created_at": m.created_at
                }
            trip_matches[trip_id]["count"] += 1

        for trip_id, data in trip_matches.items():
            trip = data["trip"]
            count = data["count"]
            dt = data["created_at"]
            activities.append({
                "type": "ROUTE_MATCH",
                "title": "New Route Match",
                "message": f"Your {trip.from_city} → {trip.to_city} trip matched {count} package request{'s' if count > 1 else ''}.",
                "created_at": dt,
                "time_ago": naturaltime(dt),
            })

        # -------------------------------------------------------------
        # 2. BOOKINGS
        # -------------------------------------------------------------
        bookings = Booking.objects.filter(traveler=user).order_by("-updated_at")[:limit]

        for b in bookings:
            pkg_name = b.title or "Package"
            dt = b.updated_at or b.created_at

            if b.status == BookingStatus.PENDING:
                activities.append({
                    "type": "BOOKING_REQUEST",
                    "title": "New Booking Request",
                    "message": f"A new booking request has been received for {pkg_name}.",
                    "created_at": b.created_at,
                    "time_ago": naturaltime(b.created_at),
                })
            elif b.status == BookingStatus.TRAVELER_ACCEPTED:
                sender_name = b.sender.get_full_name() or "a user" if b.sender else "a user"
                activities.append({
                    "type": "BOOKING_ACCEPTED",
                    "title": "Booking Accepted",
                    "message": f"You accepted a booking from {sender_name}.",
                    "created_at": dt,
                    "time_ago": naturaltime(dt),
                })
            elif b.status == BookingStatus.CONFIRMED:
                activities.append({
                    "type": "ESCROW_FUNDED",
                    "title": "Escrow Funded",
                    "message": f"Payment of ${b.agreed_reward} has been secured in escrow.",
                    "created_at": dt,
                    "time_ago": naturaltime(dt),
                })
            elif b.status == BookingStatus.PICKED_UP:
                activities.append({
                    "type": "PACKAGE_PICKED_UP",
                    "title": "Package Picked Up",
                    "message": "Sender confirmed package pickup.",
                    "created_at": dt,
                    "time_ago": naturaltime(dt),
                })
            elif b.status == BookingStatus.IN_TRANSIT:
                activities.append({
                    "type": "DELIVERY_IN_TRANSIT",
                    "title": "Delivery In Transit",
                    "message": "Your delivery is currently in transit.",
                    "created_at": dt,
                    "time_ago": naturaltime(dt),
                })
            elif b.status == BookingStatus.DELIVERED:
                activities.append({
                    "type": "PACKAGE_DELIVERED",
                    "title": "Package Delivered",
                    "message": "Package successfully delivered.",
                    "created_at": dt,
                    "time_ago": naturaltime(dt),
                })

        # -------------------------------------------------------------
        # 3. WALLET TRANSACTIONS (Escrow Release / Earnings)
        # -------------------------------------------------------------
        if hasattr(user, "wallet"):
            wallet_txs = WalletTransaction.objects.filter(
                wallet=user.wallet,
                type=WalletTransaction.TransactionType.ESCROW_RELEASE,
                status=WalletTransaction.TransactionStatus.COMPLETED
            ).order_by("-created_at")[:limit]

            for tx in wallet_txs:
                activities.append({
                    "type": "ESCROW_RELEASED",
                    "title": "Escrow Released",
                    "message": f"${tx.amount} has been added to your wallet.",
                    "created_at": tx.created_at,
                    "time_ago": naturaltime(tx.created_at),
                })

        # -------------------------------------------------------------
        # 4. WITHDRAWAL REQUESTS
        # -------------------------------------------------------------
        if hasattr(user, "wallet"):
            withdrawals = WithdrawalRequest.objects.filter(
                wallet=user.wallet
            ).order_by("-updated_at")[:limit]

            for w in withdrawals:
                dt = w.updated_at or w.created_at

                if w.status == WithdrawalRequest.WithdrawalStatus.PENDING:
                    activities.append({
                        "type": "WITHDRAWAL_REQUESTED",
                        "title": "Withdrawal Requested",
                        "message": f"Withdrawal request for ${w.amount} submitted.",
                        "created_at": w.created_at,
                        "time_ago": naturaltime(w.created_at),
                    })
                elif w.status == WithdrawalRequest.WithdrawalStatus.COMPLETED:
                    activities.append({
                        "type": "WITHDRAWAL_COMPLETED",
                        "title": "Withdrawal Completed",
                        "message": f"${w.amount} has been transferred successfully.",
                        "created_at": w.completed_at or dt,
                        "time_ago": naturaltime(w.completed_at or dt),
                    })
                elif w.status == WithdrawalRequest.WithdrawalStatus.REJECTED:
                    activities.append({
                        "type": "WITHDRAWAL_REJECTED",
                        "title": "Withdrawal Rejected",
                        "message": f"Withdrawal request for ${w.amount} was rejected.",
                        "created_at": dt,
                        "time_ago": naturaltime(dt),
                    })

        # Combine and sort all activities chronologically descending
        activities.sort(key=lambda x: x["created_at"], reverse=True)
        final_activities = activities[:limit]

        serializer = CompactActivitySerializer(final_activities, many=True)

        return Response(
            {
                "success": True,
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )