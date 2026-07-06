from rest_framework import serializers
from .models import Review
# Assuming your Booking model is accessible like this, adjust if necessary
# from bookings.models import Booking 

class ReviewSerializer(serializers.ModelSerializer):
    # Read-only fields to prevent tampering during creation
    id = serializers.UUIDField(read_only=True)
    sender = serializers.PrimaryKeyRelatedField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Review
        fields = [
            'id',
            'booking',
            'sender',
            'traveler',
            'rating',
            'comment',
            'created_at',
            'updated_at',
        ]

    def validate(self, attrs):
        """
        Object-level validation to enforce business rules before database hits.
        """
        # 1. Fetch the sender from the request context
        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError(
                {"detail": "Authentication credentials were not provided."}
            )
        
        sender = request.user
        booking = attrs.get('booking')
        traveler = attrs.get('traveler')

        # If performing an update, partial data might be passed
        if self.instance:
            booking = booking or self.instance.booking
            traveler = traveler or self.instance.traveler
            sender = self.instance.sender  # Senders shouldn't change on update

        # 2. Verify that the sender owns the booking
        if booking.sender != sender:
            raise serializers.ValidationError(
                {"booking": "Only the verified booking sender can submit this review."}
            )

        # 3. Verify that the traveler matches the booking
        if booking.traveler != traveler:
            raise serializers.ValidationError(
                {"traveler": "The selected traveler does not match the traveler assigned to this booking."}
            )

        # 4. Verify booking completion status
        # Note: If your status field is a ChoiceField/Enum, ensure 'COMPLETED' matches exactly
        if booking.status != "COMPLETED":
            raise serializers.ValidationError(
                {"booking": "Reviews can only be submitted after the booking has been marked as COMPLETED."}
            )

        # 5. Check for UniqueConstraint on creation
        if not self.instance:
            if Review.objects.filter(booking=booking, sender=sender).exists():
                raise serializers.ValidationError(
                    {"booking": "You have already submitted a review for this booking."}
                )

        return attrs

    def create(self, validated_data):
        """
        Inject the authenticated request user as the sender automatically.
        """
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)