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
    

    

class InvoiceDownloadView(APIView):
    """
    GET /invoices/<id>/download/
    Generates PDF once, caches to file storage, tracks downloads.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            invoice = Invoice.objects.select_related(
                "booking", "sender", "traveler", "package", "trip", "payment"
            ).get(id=id)
            
            if invoice.sender != request.user and invoice.traveler != request.user:
                return Response({"error": "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
        except Invoice.DoesNotExist:
            return Response({"error": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

        # Update download analytics timestamp tracking
        invoice.last_downloaded_at = timezone.now()

        # If a generated invoice document file already exists in storage, serve it directly
        if invoice.pdf:
            invoice.save(update_fields=['last_downloaded_at'])
            return FileResponse(invoice.pdf.open(), content_type="application/pdf")

        # Fallback: Generate the text-receipt layout if it doesn't exist yet
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=54, bottomMargin=54)
        styles = getSampleStyleSheet()
        
        receipt_text = ParagraphStyle('RecText', fontName='Courier', fontSize=10, leading=14, textColor=colors.black)
        receipt_center = ParagraphStyle('RecCent', parent=receipt_text, alignment=1)
        receipt_right = ParagraphStyle('RecRight', parent=receipt_text, alignment=2)
        receipt_bold = ParagraphStyle('RecBold', parent=receipt_text, fontName='Courier-Bold')

        elements = []
        elements.append(Paragraph("+------------------------------------------------------------+", receipt_center))
        elements.append(Paragraph("<b>LUGGAGELINKER</b>", ParagraphStyle('T', parent=receipt_center, fontSize=12, fontName='Courier-Bold')))
        elements.append(Paragraph("Package Delivery Marketplace", receipt_center))
        elements.append(Paragraph("+------------------------------------------------------------+", receipt_center))
        elements.append(Spacer(1, 12))

        # Dynamic Status Reading directly via Payment Source of truth!
        meta_data = [
            [Paragraph("Invoice #", receipt_text), Paragraph(f": {invoice.invoice_number}", receipt_text)],
            [Paragraph("Booking", receipt_text), Paragraph(f": {invoice.booking.booking_number}", receipt_text)],
            [Paragraph("Date", receipt_text), Paragraph(f": {invoice.invoice_date.strftime('%d %b %Y')}", receipt_text)],
            [Paragraph("Status", receipt_text), Paragraph(f": {invoice.payment.status.upper()}", receipt_bold)]
        ]
        meta_table = Table(meta_data, colWidths=[90, 370])
        meta_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 1)]))
        elements.append(meta_table)
        
        def add_div():
            elements.append(Paragraph("--------------------------------------------------------------", receipt_center))

        # Sender
        add_div()
        elements.append(Paragraph("<b>Sender</b>", receipt_bold))
        elements.append(Paragraph(f"{invoice.sender.get_full_name() or 'User'}", receipt_text))
        elements.append(Paragraph(invoice.sender.email, receipt_text))

        # Traveler
        add_div()
        elements.append(Paragraph("<b>Traveler</b>", receipt_bold))
        elements.append(Paragraph(f"{invoice.traveler.get_full_name() or 'User'}", receipt_text))
        elements.append(Paragraph(invoice.traveler.email, receipt_text))

        # Package
        add_div()
        elements.append(Paragraph("<b>Package</b>", receipt_bold))
        elements.append(Paragraph(invoice.package.title, receipt_text))
        elements.append(Paragraph(f"Weight : {getattr(invoice.package, 'weight', '2.30')} kg", receipt_text))
        elements.append(Paragraph(f"{getattr(invoice.trip, 'departure_city', 'Dhaka')} &rarr; {getattr(invoice.trip, 'arrival_city', 'Milan')}", receipt_text))

        # Financial Calculations
        add_div()
        sym = "$" if invoice.currency == "USD" else f"{invoice.currency} "
        item_data = [
            [Paragraph("Delivery Reward", receipt_text), Paragraph(f"{sym}{invoice.reward}", receipt_right)],
            [Paragraph("Platform Fee", receipt_text), Paragraph(f"{sym}{invoice.platform_fee}", receipt_right)],
            [Paragraph("-----------------------------------------", receipt_text), Paragraph("-------------", receipt_right)],
            [Paragraph("<b>Total Paid</b>", receipt_bold), Paragraph(f"<b>{sym}{invoice.total_paid}</b>", receipt_right)]
        ]
        item_table = Table(item_data, colWidths=[330, 130])
        item_table.setStyle(TableStyle([('ALIGN', (1,0), (1,-1), 'RIGHT'), ('PADDING', (0,0), (-1,-1), 1)]))
        elements.append(item_table)

        # Escrow Logic Check
        add_div()
        escrow_status = "Released" if invoice.payment.status == "CAPTURED" else "Held in Escrow"
        gateway_data = [
            [Paragraph("Payment Gateway", receipt_text), Paragraph(f": {invoice.payment_method.upper()}", receipt_text)],
            [Paragraph("Transaction ID", receipt_text), Paragraph(f": {invoice.transaction_id or 'N/A'}", receipt_text)],
            [Paragraph("Escrow", receipt_text), Paragraph(f": {escrow_status}", receipt_text)]
        ]
        gateway_table = Table(gateway_data, colWidths=[120, 340])
        elements.append(gateway_table)
        add_div()

        # Sign off
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Thank you for choosing LuggageLinker", receipt_center))
        elements.append(Paragraph("support@luggagelinker.com | www.luggagelinker.com", receipt_center))
        elements.append(Paragraph("+------------------------------------------------------------+", receipt_center))

        doc.build(elements)
        buffer.seek(0)

        # Save to storage file backend so it's cached forever
        file_name = f"Invoice_{invoice.invoice_number}.pdf"
        invoice.pdf.save(file_name, ContentFile(buffer.read()), save=False)
        invoice.save()

        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=file_name, content_type="application/pdf")