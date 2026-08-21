from django.shortcuts import render

# Create your views here.
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.bookings.models import Booking
from django.utils import timezone

from .models import Negotiation,NegotiationOffer
from .enums import NegotiationStatus,OfferStatus



class CreateNegotiationOfferAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    @transaction.atomic
    def post(
        self,
        request,
        negotiation_id,
    ):

        negotiation = (
            Negotiation.objects
            .select_for_update()
            .select_related(
                "booking",
                "sender",
                "traveler",
            )
            .filter(
                id=negotiation_id,
                status=NegotiationStatus.ACTIVE,
            )
            .first()
        )

        if not negotiation:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Active negotiation not found."
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------------
        # User must belong to negotiation
        # -----------------------------------------------

        if request.user.id not in [
            negotiation.sender_id,
            negotiation.traveler_id,
        ]:

            return Response(
                {
                    "success": False,
                    "message": (
                        "You are not part of "
                        "this negotiation."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        amount = request.data.get(
            "amount"
        )

        if amount is None:

            return Response(
                {
                    "success": False,
                    "message": "Amount is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:

            amount = Decimal(
                str(amount)
            )

        except Exception:

            return Response(
                {
                    "success": False,
                    "message": "Invalid amount.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if amount <= 0:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Amount must be greater than zero."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -----------------------------------------------
        # Previous pending offer
        # becomes countered
        # -----------------------------------------------

        (
            negotiation.offers
            .filter(
                status=OfferStatus.PENDING
            )
            .update(
                status=OfferStatus.COUNTERED
            )
        )

        # -----------------------------------------------
        # Create new offer
        # -----------------------------------------------

        offer = NegotiationOffer.objects.create(

            negotiation=negotiation,

            offered_by=request.user,

            amount=amount,

            currency=negotiation.currency,

            status=OfferStatus.PENDING,

            message=request.data.get(
                "message",
                "",
            ),
        )

        return Response(
            {
                "success": True,
                "message": (
                    "Offer created successfully."
                ),
                "data": {
                    "id": str(
                        offer.id
                    ),
                    "amount": str(
                        offer.amount
                    ),
                    "currency": (
                        offer.currency
                    ),
                    "status": (
                        offer.status
                    ),
                    "message": (
                        offer.message
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class StartNegotiationAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    @transaction.atomic
    def post(self, request, booking_id):

        booking = (
            Booking.objects
            .select_for_update()
            .select_related(
                "sender",
                "traveler",
            )
            .filter(
                id=booking_id
            )
            .first()
        )

        if not booking:

            return Response(
                {
                    "success": False,
                    "message": "Booking not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Sender only

        if booking.sender_id != request.user.id:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Only the sender can "
                        "start negotiation."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Existing negotiation

        if hasattr(booking, "negotiation"):

            return Response(
                {
                    "success": False,
                    "message": (
                        "Negotiation already exists."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------------------------------
        # IMPORTANT
        # Get original price from booking
        # ------------------------------------------------

        original_price = booking.total_amount

        if original_price is None:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Booking price is not available."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        negotiation = Negotiation.objects.create(

            booking=booking,

            sender=booking.sender,

            traveler=booking.traveler,

            original_price=original_price,

            currency=booking.currency,

            status=NegotiationStatus.ACTIVE,
        )

        return Response(
            {
                "success": True,
                "message": (
                    "Negotiation started successfully."
                ),
                "data": {
                    "id": str(
                        negotiation.id
                    ),
                    "booking_id": str(
                        booking.id
                    ),
                    "original_price": str(
                        negotiation.original_price
                    ),
                    "currency": (
                        negotiation.currency
                    ),
                    "status": (
                        negotiation.status
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AcceptNegotiationOfferAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    @transaction.atomic
    def post(
        self,
        request,
        negotiation_id,
        offer_id,
    ):

        negotiation = (
            Negotiation.objects
            .select_for_update()
            .select_related(
                "booking",
            )
            .filter(
                id=negotiation_id,
                status=NegotiationStatus.ACTIVE,
            )
            .first()
        )

        if not negotiation:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Active negotiation not found."
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        offer = (
            NegotiationOffer.objects
            .select_for_update()
            .filter(
                id=offer_id,
                negotiation=negotiation,
                status=OfferStatus.PENDING,
            )
            .first()
        )

        if not offer:

            return Response(
                {
                    "success": False,
                    "message": (
                        "Pending offer not found."
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------------
        # Cannot accept own offer
        # -----------------------------------------------

        if offer.offered_by_id == request.user.id:

            return Response(
                {
                    "success": False,
                    "message": (
                        "You cannot accept your "
                        "own offer."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -----------------------------------------------
        # User must belong to negotiation
        # -----------------------------------------------

        if request.user.id not in [
            negotiation.sender_id,
            negotiation.traveler_id,
        ]:

            return Response(
                {
                    "success": False,
                    "message": (
                        "You are not part of "
                        "this negotiation."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -----------------------------------------------
        # Accept
        # -----------------------------------------------

        offer.status = OfferStatus.ACCEPTED

        offer.save(
            update_fields=[
                "status",
            ]
        )

        negotiation.agreed_price = (
            offer.amount
        )

        negotiation.status = (
            NegotiationStatus.ACCEPTED
        )

        negotiation.completed_at = (
            timezone.now()
        )

        negotiation.save(
            update_fields=[
                "agreed_price",
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        # -----------------------------------------------
        # Cancel all other pending offers
        # -----------------------------------------------

        (
            negotiation.offers
            .filter(
                status=OfferStatus.PENDING
            )
            .exclude(
                id=offer.id
            )
            .update(
                status=OfferStatus.CANCELLED
            )
        )

        return Response(
            {
                "success": True,
                "message": (
                    "Negotiation accepted."
                ),
                "data": {
                    "negotiation_id": str(
                        negotiation.id
                    ),
                    "agreed_price": str(
                        negotiation.agreed_price
                    ),
                    "currency": (
                        negotiation.currency
                    ),
                    "status": (
                        negotiation.status
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )