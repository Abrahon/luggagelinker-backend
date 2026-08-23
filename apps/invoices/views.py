import io
from django.db import models  # <-- Added missing models import for Q queries
from django.http import FileResponse
from django.utils import timezone
from django.core.files.base import ContentFile
from rest_framework import generics, status  # <-- Added missing generics import
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated  # <-- Added missing permission import

# ReportLab Engine Elements
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from apps.invoices.models import Invoice, InvoiceStatus
from apps.invoices.serializers import InvoiceSerializer

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from apps.invoices.models import Invoice

from django.db import models
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.invoices.models import Invoice
from apps.invoices.serializers import InvoiceSerializer


class InvoiceListView(generics.ListAPIView):
    """
    GET /invoices/
    Returns all invoices related to the logged-in user with standard success wrapping.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Invoice.objects.filter(
            models.Q(sender=user) | models.Q(traveler=user)
        ).select_related(
            "booking", "payment", "sender__profile", "traveler__profile", "package"
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Handle pagination smoothly if added in settings later
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "message": "Invoices retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class InvoiceDetailView(generics.RetrieveAPIView):
    """
    GET /invoices/<uuid:id>/
    Returns single invoice details or a clean error if unauthorized or non-existent.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        return Invoice.objects.filter(
            models.Q(sender=user) | models.Q(traveler=user)
        ).select_related(
            "booking", "payment", "sender__profile", "traveler__profile", "package", "trip"
        )

    def retrieve(self, request, *args, **kwargs):
        try:
            # Re-fetches instance using the query isolation scope from get_queryset()
            instance = self.get_object()
        except Exception:
            return Response({
                "success": False,
                "error": "Invoice not found, or you do not have permission to view it."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "message": "Invoice details retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
    

    

# ReportLab Engine Elements

from django.utils import timezone
from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.invoices.models import Invoice


class InvoiceDownloadView(APIView):
    """
    Download an invoice PDF.

    GET /invoices/<uuid:id>/download/

    The PDF is returned as an attachment so the browser
    downloads the file.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, id):

        # =========================================================
        # GET INVOICE
        # =========================================================

        try:
            invoice = (
                Invoice.objects
                .select_related(
                    "booking",
                    "payment",
                    "sender",
                    "traveler",
                    "package",
                    "trip",
                )
                .get(id=id)
            )

        except Invoice.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Invoice not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================================================
        # AUTHORIZATION
        # =========================================================

        if (
            invoice.sender_id != request.user.id
            and invoice.traveler_id != request.user.id
        ):
            return Response(
                {
                    "success": False,
                    "message": (
                        "You do not have permission "
                        "to download this invoice."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =========================================================
        # CHECK PDF
        # =========================================================

        if not invoice.pdf:
            return Response(
                {
                    "success": False,
                    "message": "Invoice PDF is not available.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================================================
        # TRACK DOWNLOAD
        # =========================================================

        invoice.last_downloaded_at = timezone.now()

        invoice.save(
            update_fields=["last_downloaded_at"]
        )

        # =========================================================
        # RETURN PDF AS DOWNLOAD
        # =========================================================

        return FileResponse(
            invoice.pdf.open("rb"),
            as_attachment=True,
            filename=f"Invoice_{invoice.invoice_number}.pdf",
            content_type="application/pdf",
        )


from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.payment.models import BookingPayment
from apps.invoices.serializers import InvoiceSerializer


class AdminPaymentInvoiceDetailView(generics.RetrieveAPIView):

    permission_classes = [IsAdminUser]
    lookup_field = "id"

    queryset = BookingPayment.objects.select_related(
        "invoice",
        "invoice__package",
        "invoice__trip",
        "invoice__booking",
        "invoice__sender__profile",
        "invoice__traveler__profile",
    )

    def retrieve(self, request, *args, **kwargs):
        payment = self.get_object()

        invoice = getattr(payment, "invoice", None)

        if invoice is None:
            return Response(
                {
                    "success": False,
                    "message": "No invoice found for this payment.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminPaymentInvoiceDetailSerializer(
            invoice,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "message": "Invoice retrieved successfully.",
                "data": serializer.data,
            }
        )





class AdminPaymentInvoiceDownloadView(APIView):
    """
    GET admin/payments/<uuid:id>/invoice/download/
    Allows Admin users to download an invoice PDF using the BookingPayment UUID.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        try:
            payment = BookingPayment.objects.select_related(
                "invoice",
                "invoice__package",
                "invoice__trip",
                "invoice__booking",
                "invoice__sender__profile",
                "invoice__traveler__profile",
            ).get(id=id)
        except BookingPayment.DoesNotExist:
            return Response(
                {"success": False, "message": "Payment record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        invoice = getattr(payment, "invoice", None)
        if invoice is None:
            return Response(
                {"success": False, "message": "No invoice found for this payment."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Update download tracking timestamp
        invoice.last_downloaded_at = timezone.now()

        # 1. Serve cached PDF if already generated and saved
        if invoice.pdf:
            invoice.save(update_fields=["last_downloaded_at"])
            return FileResponse(
                invoice.pdf.open(),
                as_attachment=True,
                filename=f"Invoice_{invoice.invoice_number}.pdf",
                content_type="application/pdf",
            )

        # 2. Dynamic PDF Generation using ReportLab
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        # Styles
        receipt_text = ParagraphStyle(
            "RecText", fontName="Courier", fontSize=9, leading=13, textColor=colors.black
        )
        receipt_center = ParagraphStyle("RecCent", parent=receipt_text, alignment=1)
        receipt_right = ParagraphStyle("RecRight", parent=receipt_text, alignment=2)
        receipt_bold = ParagraphStyle("RecBold", parent=receipt_text, fontName="Courier-Bold")

        elements = []

        # Header
        elements.append(Paragraph("+-------------------------------------------------------------------+", receipt_center))
        elements.append(
            Paragraph(
                "<b>LUGGAGELINKER - OFFICIAL DELIVERY RECEIPT</b>",
                ParagraphStyle("T", parent=receipt_center, fontSize=11, fontName="Courier-Bold"),
            )
        )
        elements.append(Paragraph("Peer-to-Peer Logistics & Parcel Delivery Network", receipt_center))
        elements.append(Paragraph("+-------------------------------------------------------------------+", receipt_center))
        elements.append(Spacer(1, 10))

        def add_div():
            elements.append(Paragraph("--------------------------------------------------------------------", receipt_center))

        # Metadata Section
        pay_status_display = payment.get_status_display() if payment else "N/A"
        tracking_num = getattr(invoice.booking, "tracking_number", "N/A")

        meta_data = [
            [Paragraph("Invoice Number", receipt_bold), Paragraph(f": {invoice.invoice_number}", receipt_text)],
            [Paragraph("Tracking Number", receipt_bold), Paragraph(f": {tracking_num}", receipt_text)],
            [Paragraph("Issue Date", receipt_bold), Paragraph(f": {invoice.invoice_date.strftime('%d %b %Y, %H:%M UTC')}", receipt_text)],
            [Paragraph("Payment Status", receipt_bold), Paragraph(f": {pay_status_display}", receipt_bold)],
        ]
        meta_table = Table(meta_data, colWidths=[120, 384])
        meta_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 1)]))
        elements.append(meta_table)

        # Route & Transit Details
        add_div()
        elements.append(Paragraph("<b>1. ROUTE & TRANSIT DETAILS</b>", receipt_bold))

        from_city = getattr(invoice.trip, "from_city", "N/A")
        to_city = getattr(invoice.trip, "to_city", "N/A")
        from_country = getattr(invoice.trip, "from_country", "")
        to_country = getattr(invoice.trip, "to_country", "")
        
        dep_date = getattr(invoice.trip, "departure_date", None)
        arr_date = getattr(invoice.trip, "arrival_date", None)

        formatted_dep_date = dep_date.strftime("%d %b %Y") if dep_date else "N/A"
        formatted_arr_date = arr_date.strftime("%d %b %Y") if arr_date else "N/A"

        route_data = [
            [Paragraph("Route", receipt_text), Paragraph(f": {from_city}, {from_country} ==> {to_city}, {to_country}", receipt_bold)],
            [Paragraph("Departure Date", receipt_text), Paragraph(f": {formatted_dep_date}", receipt_text)],
            [Paragraph("Arrival Date", receipt_text), Paragraph(f": {formatted_arr_date}", receipt_text)],
        ]
        route_table = Table(route_data, colWidths=[120, 384])
        route_table.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 1)]))
        elements.append(route_table)

        # Parcel Specifications
        add_div()
        elements.append(Paragraph("<b>2. PRODUCT & PARCEL SPECIFICATIONS</b>", receipt_bold))

        pkg_title = getattr(invoice.package, "title", "General Parcel")
        pkg_category = (
            invoice.package.get_category_display()
            if hasattr(invoice.package, "get_category_display")
            else "Standard Cargo"
        )
        pkg_weight = getattr(invoice.package, "weight", "0.00")
        pkg_desc = getattr(invoice.package, "description", "No description provided.")

        item_data = [
            [Paragraph("Item Name", receipt_text), Paragraph(f": {pkg_title}", receipt_bold)],
            [Paragraph("Category", receipt_text), Paragraph(f": {pkg_category}", receipt_text)],
            [Paragraph("Delivered Weight", receipt_text), Paragraph(f": {pkg_weight} kg", receipt_bold)],
            [Paragraph("Item Description", receipt_text), Paragraph(f": {pkg_desc[:120]}", receipt_text)],
        ]
        item_table = Table(item_data, colWidths=[120, 384])
        item_table.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 1)]))
        elements.append(item_table)

        # Participants Directory
        add_div()
        elements.append(Paragraph("<b>3. PARTICIPANTS DIRECTORY</b>", receipt_bold))
        sender_name = (
            invoice.sender.get_full_name()
            if hasattr(invoice.sender, "get_full_name")
            else invoice.sender.email
        )
        traveler_name = (
            invoice.traveler.get_full_name()
            if hasattr(invoice.traveler, "get_full_name")
            else invoice.traveler.email
        )

        user_data = [
            [Paragraph("Sender (Client)", receipt_text), Paragraph(f": {sender_name} ({invoice.sender.email})", receipt_text)],
            [Paragraph("Traveler (Courier)", receipt_text), Paragraph(f": {traveler_name} ({invoice.traveler.email})", receipt_text)],
        ]
        user_table = Table(user_data, colWidths=[120, 384])
        user_table.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 1)]))
        elements.append(user_table)

        # Financial Breakdown
        add_div()
        elements.append(Paragraph("<b>4. FINANCIAL BREAKDOWN</b>", receipt_bold))
        sym = "$" if invoice.currency == "USD" else f"{invoice.currency} "

        financial_data = [
            [Paragraph("Traveler Delivery Reward", receipt_text), Paragraph(f"{sym}{invoice.reward}", receipt_right)],
            [Paragraph("Platform Fee", receipt_text), Paragraph(f"{sym}{invoice.platform_fee}", receipt_right)],
            [Paragraph("------------------------------------------", receipt_text), Paragraph("------------", receipt_right)],
            [Paragraph("<b>TOTAL AMOUNT PAID</b>", receipt_bold), Paragraph(f"<b>{sym}{invoice.total_paid}</b>", receipt_right)],
        ]
        financial_table = Table(financial_data, colWidths=[370, 134])
        financial_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 1)]))
        elements.append(financial_table)

        # Payment Details
        add_div()
        pay_info = [
            [Paragraph("Payment Gateway", receipt_text), Paragraph(f": {invoice.get_payment_method_display()}", receipt_text)],
            [Paragraph("Transaction Ref", receipt_text), Paragraph(f": {invoice.transaction_id or 'N/A'}", receipt_text)],
        ]
        pay_table = Table(pay_info, colWidths=[120, 384])
        pay_table.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 1)]))
        elements.append(pay_table)
        add_div()

        # Footer
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Thank you for using LuggageLinker Marketplace!", receipt_center))
        elements.append(Paragraph("Questions? Contact support@luggagelinker.com", receipt_center))
        elements.append(Paragraph("+-------------------------------------------------------------------+", receipt_center))

        doc.build(elements)
        buffer.seek(0)

        # Save generated file to storage field for future downloads
        file_name = f"Invoice_{invoice.invoice_number}.pdf"
        invoice.pdf.save(file_name, ContentFile(buffer.read()), save=False)
        invoice.save()

        buffer.seek(0)
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=file_name,
            content_type="application/pdf",
        )

from django.http import FileResponse
class InvoiceViewPDFView(APIView):
    """
    View an invoice PDF directly in the browser.

    GET /invoices/<uuid:id>/view/

    The PDF is opened inline in the browser.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, id):

        # =========================================================
        # GET INVOICE
        # =========================================================

        try:
            invoice = (
                Invoice.objects
                .select_related(
                    "booking",
                    "payment",
                    "sender",
                    "traveler",
                    "package",
                    "trip",
                )
                .get(id=id)
            )

        except Invoice.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Invoice not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================================================
        # AUTHORIZATION
        # =========================================================

        if (
            invoice.sender_id != request.user.id
            and invoice.traveler_id != request.user.id
        ):
            return Response(
                {
                    "success": False,
                    "message": (
                        "You do not have permission "
                        "to view this invoice."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =========================================================
        # CHECK PDF
        # =========================================================

        if not invoice.pdf:
            return Response(
                {
                    "success": False,
                    "message": "Invoice PDF is not available.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================================================
        # RETURN PDF INLINE
        # =========================================================

        return FileResponse(
            invoice.pdf.open("rb"),
            as_attachment=False,
            filename=f"Invoice_{invoice.invoice_number}.pdf",
            content_type="application/pdf",
        )