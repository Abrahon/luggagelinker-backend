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
    category = serializers.CharField(source="get_category_display", read_only=True)
    weight = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    description = serializers.CharField(read_only=True)


class TripDetailSerializer(serializers.Serializer):
    """
    Nested serializer matching the Trip model fields.
    """
    id = serializers.UUIDField(read_only=True)
    from_city = serializers.CharField(read_only=True)
    to_city = serializers.CharField(read_only=True)
    
    # Corrected: Use DateField to match models.DateField()
    departure_date = serializers.DateField(read_only=True)
    arrival_date = serializers.DateField(read_only=True)


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
    payment_status = serializers.CharField(source="payment.status", read_only=True)
    
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

class AdminPaymentInvoiceDetailSerializer(InvoiceSerializer):
    sender = InvoiceUserSerializer(read_only=True)
    traveler = InvoiceUserSerializer(read_only=True)

    package = serializers.SerializerMethodField()
    trip = serializers.SerializerMethodField()
    booking = serializers.SerializerMethodField()

    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + (
            "package",
            "trip",
            "booking",
        )

    def get_package(self, obj):
        package = getattr(obj, "package", None)
        if not package:
            return None

        return {
            "id": package.id,
            "title": package.title,
            "description": package.description,
            "category": package.get_category_display() if hasattr(package, "get_category_display") else None,
            "weight": package.weight,
            "declared_value": getattr(package, "declared_value", None),
            "currency": getattr(package, "currency", None),
            "pickup_country": getattr(package, "pickup_country", None),
            "pickup_city": getattr(package, "pickup_city", None),
            "pickup_address": getattr(package, "pickup_address", None),
            "destination_country": getattr(package, "destination_country", None),
            "destination_city": getattr(package, "destination_city", None),
            "destination_address": getattr(package, "destination_address", None),
            "pickup_date": getattr(package, "pickup_date", None),
            "latest_delivery_date": getattr(package, "latest_delivery_date", None),
        }

    def get_trip(self, obj):
        trip = getattr(obj, "trip", None)
        if not trip:
            return None

        return {
            "id": trip.id,
            "from_country": getattr(trip, "from_country", None),
            "from_city": getattr(trip, "from_city", None),
            "to_country": getattr(trip, "to_country", None),
            "to_city": getattr(trip, "to_city", None),
            "departure_date": getattr(trip, "departure_date", None),
            "arrival_date": getattr(trip, "arrival_date", None),
            "transport_type": getattr(trip, "transport_type", None),
        }

    def get_booking(self, obj):
        booking = getattr(obj, "booking", None)
        if not booking:
            return None

        return {
            "id": booking.id,
            "tracking_number": getattr(booking, "tracking_number", None),
            "status": getattr(booking, "status", None),
            "created_at": getattr(booking, "created_at", None),
            "updated_at": getattr(booking, "updated_at", None),
        }