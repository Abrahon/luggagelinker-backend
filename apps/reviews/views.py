from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from .models import Review
from .serializers import ReviewSerializer
from django.db import transaction

from apps.reviews.services import update_traveler_rating
from apps.notifications.services import notify_review_received


class ReviewListCreateAPIView(generics.ListCreateAPIView):
    """
    API view to list reviews and create a new review.
    
    * Senders can only see reviews they have submitted.
    * Automatically handles injecting the request user into the creation cycle.
    """
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Optimized queryset ensuring users only view relevant reviews.
        Uses select_related to minimize DB hits on related booking fields.
        """
        user = self.request.user
        
        # Senders see what they wrote; Travelers see reviews about them.
        # If you want Senders to ONLY see their submitted reviews, keep it as:
        # return Review.objects.filter(sender=user).select_related('booking', 'sender', 'traveler')
        return Review.objects.filter(
            Q(sender=user) | Q(traveler=user)
        ).select_related('booking', 'sender', 'traveler')

    def perform_create(self, serializer):
        """
        Save the review, then update traveler rating and
        send a notification after the transaction commits.
        """

        review = serializer.save()

        transaction.on_commit(
            lambda: update_traveler_rating(
                traveler=review.traveler,
                rating=review.rating,
            )
        )

        transaction.on_commit(
            lambda: notify_review_received(
                traveler=review.traveler,
                sender=review.sender,
                review=review,
            )
        )


class ReviewRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update, or delete a specific review instance.
    
    * Only the original sender can update or delete their review.
    * Both sender and traveler can view (retrieve) it.
    """
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Optimizes database retrieval.
        """
        user = self.request.user
        return Review.objects.filter(
            Q(sender=user) | Q(traveler=user)
        ).select_related('booking', 'sender', 'traveler')

    def perform_update(self, serializer):
        """
        Object-level permission guard to ensure only the original author 
        (sender) can modify the review content.
        """
        review = self.get_object()
        if review.sender != self.request.user:
            raise PermissionDenied("You do not have permission to edit this review.")
        serializer.save()

    def perform_destroy(self, instance):
        """
        Object-level permission guard to ensure only the original author
        (sender) can delete the review.
        """
        if instance.sender != self.request.user:
            raise PermissionDenied("You do not have permission to delete this review.")
        instance.delete()