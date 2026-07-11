from django.shortcuts import render

# Create your views here.
from django.db.models import Count
from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

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