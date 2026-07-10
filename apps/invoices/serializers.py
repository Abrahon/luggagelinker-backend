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
            return f"{first} {last}".strip() or obj.email.split('@')[0]
        return obj.email.split('@')[0]


class InvoiceSerializer(serializers.ModelSerializer):
    # Nested user objects
    sender = InvoiceUserSerializer(read_only=True)
    traveler = InvoiceUserSerializer(read_only=True)
    
    # Direct model string references
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True)
    package_title = serializers.CharField(source="package.title", read_only=True)
    
    # Payment status mappings straight from the BookingPayment source of truth
    payment_status = serializers.CharField(source="payment.status", read_only=True)
    
    # Human-readable displays for choices strings
    invoice_lifecycle_status = serializers.CharField(source="get_status_display", read_only=True)
    payment_gateway_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    
    # Cloudinary/S3 storage URL resolution helper
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            "id",
            "invoice_number",
            "booking_number",
            "sender",
            "traveler",
            "package_title",
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
        read_only_fields = "__all__"

    def get_pdf_url(self, obj):
        """Returns full absolute download path if the asset cache exists."""
        if obj.pdf:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.pdf.url)
            return obj.pdf.url
        return None