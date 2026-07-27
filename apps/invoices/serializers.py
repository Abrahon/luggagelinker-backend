from rest_framework import serializers
from apps.invoices.models import Invoice


class InvoiceUserSerializer(serializers.Serializer):
    """
    Renders clean, readable participant metadata for the invoice layout.
    """
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        if hasattr(obj, 'profile'):
            first = getattr(obj.profile, 'first_name', '')
            last = getattr(obj.profile, 'last_name', '')
            full = f"{first} {last}".strip()
            if full:
                return full
        return obj.email.split('@')[0] if obj.email else "User"


class PackageDetailSerializer(serializers.Serializer):
    """
    Nested serializer for comprehensive package delivery details.
    """
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    category = serializers.CharField(source="category.name", default="General Goods", read_only=True)
    weight = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    description = serializers.CharField(read_only=True)


class TripDetailSerializer(serializers.Serializer):
    """
    Nested serializer for route and transit details.
    """
    id = serializers.UUIDField(read_only=True)
    departure_city = serializers.CharField(read_only=True)
    arrival_city = serializers.CharField(read_only=True)
    departure_date = serializers.DateTimeField(read_only=True)
    arrival_date = serializers.DateTimeField(read_only=True)
    transport_type = serializers.CharField(read_only=True)


class InvoiceSerializer(serializers.ModelSerializer):
    # Nested participant objects
    sender = InvoiceUserSerializer(read_only=True)
    traveler = InvoiceUserSerializer(read_only=True)
    
    # Complete Package & Trip Objects
    package_details = PackageDetailSerializer(source="package", read_only=True)
    trip_details = TripDetailSerializer(source="trip", read_only=True)
    
    # Booking Reference
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True)
    
    # Payment status mapping from BookingPayment source of truth
    payment_status = serializers.CharField(source="payment.escrow_status", read_only=True)
    
    # Human-readable choice labels
    invoice_lifecycle_status = serializers.CharField(source="get_status_display", read_only=True)
    payment_gateway_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    
    # Storage download URL
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            "id",
            "invoice_number",
            "booking_number",
            "sender",
            "traveler",
            "package_details",
            "trip_details",
            "reward",
            "platform_fee",
            "total_paid",
            "currency",
            "payment_method",
            "payment_gateway_display",
            "transaction_id",
            "payment_status",
            "status",
            "invoice_lifecycle_status",
            "pdf_url",
            "last_downloaded_at",
            "invoice_date",
            "updated_at",
        )
        read_only_fields = fields

    def get_pdf_url(self, obj):
        """Returns full absolute download path if the asset cache exists."""
        if obj.pdf:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.pdf.url)
            return obj.pdf.url
        return None