from django.urls import path

from .views import (
    StartNegotiationAPIView,
    CreateNegotiationOfferAPIView,
    AcceptNegotiationOfferAPIView,
)


urlpatterns = [

    path(
        "bookings/<uuid:booking_id>/start/",
        StartNegotiationAPIView.as_view(),
        name="start-negotiation",
    ),

    path(
        "bookings/<uuid:negotiation_id>/offers/",
        CreateNegotiationOfferAPIView.as_view(),
        name="create-negotiation-offer",
    ),

    path(
        "bookings/<uuid:negotiation_id>/offers/<uuid:offer_id>/accept/",
        AcceptNegotiationOfferAPIView.as_view(),
        name="accept-negotiation-offer",
    ),
]