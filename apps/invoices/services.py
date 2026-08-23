import io
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from apps.invoices.models import Invoice, InvoiceStatus


class InvoiceService:
    """
    Handles the complete invoice lifecycle:

    1. Create invoice for completed booking
    2. Generate unique invoice number
    3. Generate invoice PDF
    4. Store PDF in invoice.pdf

    Invoice generation is idempotent:
    calling create_for_booking() multiple times for the same
    booking will not create duplicate invoices.
    """

    # =============================================================
    # CREATE INVOICE
    # =============================================================

    @classmethod
    @transaction.atomic
    def create_for_booking(cls, booking):
        """
        Create an invoice for a completed booking.

        If an invoice already exists for this booking, return
        the existing invoice.

        If the invoice exists but its PDF is missing, generate
        the PDF automatically.
        """

        # ---------------------------------------------------------
        # 1. Check existing invoice
        # ---------------------------------------------------------

        existing_invoice = (
            Invoice.objects
            .filter(booking=booking)
            .first()
        )

        if existing_invoice:

            # Existing invoice but PDF is missing
            if not existing_invoice.pdf:
                cls.generate_pdf(existing_invoice)

            return existing_invoice

        # ---------------------------------------------------------
        # 2. Validate booking
        # ---------------------------------------------------------

        cls._validate_booking(booking)

        # ---------------------------------------------------------
        # 3. Get payment
        # ---------------------------------------------------------

        payment = cls._get_payment(booking)

        # ---------------------------------------------------------
        # 4. Build invoice data
        # ---------------------------------------------------------

        invoice_data = cls._build_invoice_data(
            booking=booking,
            payment=payment,
        )

        # ---------------------------------------------------------
        # 5. Create invoice
        # ---------------------------------------------------------

        invoice = Invoice.objects.create(
            booking=booking,
            payment=payment,

            sender=invoice_data["sender"],
            traveler=invoice_data["traveler"],

            package=invoice_data["package"],
            trip=invoice_data["trip"],

            reward=invoice_data["reward"],
            platform_fee=invoice_data["platform_fee"],
            total_paid=invoice_data["total_paid"],
            currency=invoice_data["currency"],

            payment_method=invoice_data["payment_method"],
            transaction_id=invoice_data["transaction_id"],

            status=InvoiceStatus.ACTIVE,
        )

        # ---------------------------------------------------------
        # 6. Generate PDF immediately
        # ---------------------------------------------------------

        cls.generate_pdf(invoice)

        return invoice

    # =============================================================
    # VALIDATION
    # =============================================================

    @staticmethod
    def _validate_booking(booking):
        """
        Validate whether the booking is ready for invoice generation.
        """

        status_value = getattr(
            booking.status,
            "value",
            booking.status,
        )

        if status_value not in [
            "COMPLETED",
            "DELIVERED",
        ]:
            raise ValueError(
                "Invoice can only be generated after delivery is completed."
            )

    # =============================================================
    # PAYMENT
    # =============================================================

    @staticmethod
    def _get_payment(booking):
        """
        Retrieve the payment associated with the booking.
        """

        # ---------------------------------------------------------
        # Try related payment
        # ---------------------------------------------------------

        payment = getattr(
            booking,
            "payment",
            None,
        )

        # ---------------------------------------------------------
        # Fallback
        # ---------------------------------------------------------

        if payment is None:

            from apps.payment.models import BookingPayment

            payment = (
                BookingPayment.objects
                .filter(booking=booking)
                .first()
            )

        if payment is None:
            raise ValueError(
                "Cannot generate invoice because no payment was found."
            )

        return payment

    # =============================================================
    # BUILD INVOICE DATA
    # =============================================================

    @classmethod
    def _build_invoice_data(cls, booking, payment):
        """
        Build invoice relationships and financial snapshot.
        """

        # ---------------------------------------------------------
        # Sender
        # ---------------------------------------------------------

        sender = getattr(
            booking,
            "sender",
            None,
        )

        if sender is None:
            sender = getattr(
                booking,
                "package_sender",
                None,
            )

        # ---------------------------------------------------------
        # Traveler
        # ---------------------------------------------------------

        traveler = getattr(
            booking,
            "traveler",
            None,
        )

        if traveler is None:

            trip = getattr(
                booking,
                "trip",
                None,
            )

            if trip:
                traveler = getattr(
                    trip,
                    "traveler",
                    None,
                )

        # ---------------------------------------------------------
        # Package
        # ---------------------------------------------------------

        package = getattr(
            booking,
            "package",
            None,
        )

        if package is None:

            booking_request = getattr(
                booking,
                "booking_request",
                None,
            )

            if booking_request:
                package = getattr(
                    booking_request,
                    "package",
                    None,
                )

        # ---------------------------------------------------------
        # Trip
        # ---------------------------------------------------------

        trip = getattr(
            booking,
            "trip",
            None,
        )

        # ---------------------------------------------------------
        # Validation
        # ---------------------------------------------------------

        if sender is None:
            raise ValueError(
                "Cannot generate invoice: sender not found."
            )

        if traveler is None:
            raise ValueError(
                "Cannot generate invoice: traveler not found."
            )

        if package is None:
            raise ValueError(
                "Cannot generate invoice: package not found."
            )

        if trip is None:
            raise ValueError(
                "Cannot generate invoice: trip not found."
            )

        # =========================================================
        # FINANCIAL SNAPSHOT
        # =========================================================

        reward = cls._get_decimal(
            payment,
            [
                "traveler_reward",
                "reward",
                "amount_to_traveler",
            ],
            default=Decimal("0.00"),
        )

        platform_fee = cls._get_decimal(
            payment,
            [
                "platform_fee",
                "fee",
                "platform_amount",
            ],
            default=Decimal("0.00"),
        )

        total_paid = cls._get_decimal(
            payment,
            [
                "amount",
                "total_amount",
                "amount_paid",
            ],
            default=reward + platform_fee,
        )

        # ---------------------------------------------------------
        # Currency
        # ---------------------------------------------------------

        currency = (
            getattr(
                payment,
                "currency",
                None,
            )
            or "USD"
        )

        # ---------------------------------------------------------
        # Payment method
        # ---------------------------------------------------------

        payment_method = getattr(
            payment,
            "gateway",
            None,
        )

        if payment_method is None:
            payment_method = getattr(
                payment,
                "payment_method",
                "UNKNOWN",
            )

        payment_method = getattr(
            payment_method,
            "value",
            payment_method,
        )

        # ---------------------------------------------------------
        # Transaction ID
        # ---------------------------------------------------------

        transaction_id = (
            getattr(
                payment,
                "transaction_id",
                None,
            )
            or getattr(
                payment,
                "gateway_payment_id",
                None,
            )
            or getattr(
                payment,
                "stripe_payment_intent_id",
                None,
            )
            or ""
        )

        return {
            "sender": sender,
            "traveler": traveler,
            "package": package,
            "trip": trip,

            "reward": reward,
            "platform_fee": platform_fee,
            "total_paid": total_paid,
            "currency": currency,

            "payment_method": payment_method,
            "transaction_id": transaction_id,
        }

    # =============================================================
    # DECIMAL HELPER
    # =============================================================

    @staticmethod
    def _get_decimal(
        obj,
        field_names,
        default=Decimal("0.00"),
    ):
        """
        Return the first valid Decimal field.
        """

        for field_name in field_names:

            value = getattr(
                obj,
                field_name,
                None,
            )

            if value is not None:

                try:
                    return Decimal(str(value))
                except Exception:
                    continue

        return default

    # =============================================================
    # PROFILE NAME HELPER
    # =============================================================

    @staticmethod
    def _get_user_display_name(user):
        """
        Get user's display name from the related Profile.

        User model:
            - email

        Profile model:
            - first_name
            - last_name
            - full_name property

        Priority:
            1. Profile.full_name
            2. Profile first_name + last_name
            3. User.email
            4. N/A
        """

        if not user:
            return "N/A"

        # ---------------------------------------------------------
        # Get related profile
        # ---------------------------------------------------------

        profile = getattr(user, "profile", None)

        if profile:

            # Profile.full_name property
            full_name = getattr(profile, "full_name", None)

            if full_name:
                return str(full_name).strip()

            # Extra safety: first_name + last_name
            first_name = (
                getattr(profile, "first_name", None)
                or ""
            ).strip()

            last_name = (
                getattr(profile, "last_name", None)
                or ""
            ).strip()

            full_name = f"{first_name} {last_name}".strip()

            if full_name:
                return full_name

        # ---------------------------------------------------------
        # Fallback to User.email
        # ---------------------------------------------------------

        email = getattr(user, "email", None)

        if email:
            return email

        return "N/A"

    # =============================================================
    # PDF GENERATION
    # =============================================================

    @classmethod
    def generate_pdf(cls, invoice):
        """
        Generate and permanently store the invoice PDF.

        If PDF already exists, it will not be regenerated.
        """

        # ---------------------------------------------------------
        # Prevent unnecessary regeneration
        # ---------------------------------------------------------

        if invoice.pdf:
            return invoice

        buffer = io.BytesIO()

        document = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=45,
            leftMargin=45,
            topMargin=45,
            bottomMargin=45,
            title=(
                f"LuggageLinker Invoice "
                f"{invoice.invoice_number}"
            ),
            author="LuggageLinker",
        )

        # =========================================================
        # STYLES
        # =========================================================

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=5,
        )

        subtitle_style = ParagraphStyle(
            "InvoiceSubtitle",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
        )

        section_style = ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontSize=10,
            leading=13,
            spaceBefore=8,
            spaceAfter=5,
        )

        normal_style = ParagraphStyle(
            "NormalInvoice",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
        )

        right_style = ParagraphStyle(
            "RightInvoice",
            parent=normal_style,
            alignment=TA_RIGHT,
        )

        bold_style = ParagraphStyle(
            "BoldInvoice",
            parent=normal_style,
            fontName="Helvetica-Bold",
        )

        # =========================================================
        # STORY
        # =========================================================

        elements = []

        # =========================================================
        # HEADER
        # =========================================================

        elements.append(
            Paragraph(
                "LUGGAGELINKER",
                title_style,
            )
        )

        elements.append(
            Paragraph(
                "Official Delivery Invoice",
                subtitle_style,
            )
        )

        elements.append(
            Paragraph(
                "Peer-to-Peer Logistics & Parcel Delivery Network",
                subtitle_style,
            )
        )

        elements.append(
            Spacer(1, 15)
        )

        # =========================================================
        # INVOICE INFORMATION
        # =========================================================

        invoice_info = [
            [
                Paragraph(
                    "<b>Invoice Number</b>",
                    normal_style,
                ),
                Paragraph(
                    str(invoice.invoice_number),
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Invoice Date</b>",
                    normal_style,
                ),
                Paragraph(
                    invoice.invoice_date.strftime(
                        "%d %b %Y, %H:%M UTC"
                    ),
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Booking ID</b>",
                    normal_style,
                ),
                Paragraph(
                    str(invoice.booking.id),
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Invoice Status</b>",
                    normal_style,
                ),
                Paragraph(
                    invoice.get_status_display(),
                    normal_style,
                ),
            ],
        ]

        invoice_table = Table(
            invoice_info,
            colWidths=[130, 370],
        )

        invoice_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, -1),
                        colors.whitesmoke,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        elements.append(invoice_table)

        # =========================================================
        # ROUTE
        # =========================================================

        elements.append(
            Paragraph(
                "1. ROUTE & TRIP DETAILS",
                section_style,
            )
        )

        from_city = (
            getattr(
                invoice.trip,
                "from_city",
                None,
            )
            or getattr(
                invoice.trip,
                "departure_city",
                None,
            )
            or "N/A"
        )

        to_city = (
            getattr(
                invoice.trip,
                "to_city",
                None,
            )
            or getattr(
                invoice.trip,
                "arrival_city",
                None,
            )
            or "N/A"
        )

        from_country = getattr(
            invoice.trip,
            "from_country",
            "",
        )

        to_country = getattr(
            invoice.trip,
            "to_country",
            "",
        )

        departure_date = getattr(
            invoice.trip,
            "departure_date",
            None,
        )

        arrival_date = getattr(
            invoice.trip,
            "arrival_date",
            None,
        )

        route_data = [
            [
                Paragraph(
                    "Route",
                    normal_style,
                ),
                Paragraph(
                    f"{from_city}, {from_country} → "
                    f"{to_city}, {to_country}",
                    bold_style,
                ),
            ],
            [
                Paragraph(
                    "Departure",
                    normal_style,
                ),
                Paragraph(
                    departure_date.strftime(
                        "%d %b %Y"
                    )
                    if departure_date
                    else "N/A",
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "Arrival",
                    normal_style,
                ),
                Paragraph(
                    arrival_date.strftime(
                        "%d %b %Y"
                    )
                    if arrival_date
                    else "N/A",
                    normal_style,
                ),
            ],
        ]

        route_table = Table(
            route_data,
            colWidths=[130, 370],
        )

        route_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        elements.append(route_table)

        # =========================================================
        # PACKAGE
        # =========================================================

        elements.append(
            Paragraph(
                "2. PACKAGE DETAILS",
                section_style,
            )
        )

        package_title = getattr(
            invoice.package,
            "title",
            "N/A",
        )

        package_description = (
            getattr(
                invoice.package,
                "description",
                "N/A",
            )
            or "N/A"
        )

        package_weight = getattr(
            invoice.package,
            "weight",
            "N/A",
        )

        if hasattr(
            invoice.package,
            "get_category_display",
        ):
            package_category = (
                invoice.package
                .get_category_display()
            )
        else:
            package_category = getattr(
                invoice.package,
                "category",
                "N/A",
            )

        package_data = [
            [
                Paragraph(
                    "Package",
                    normal_style,
                ),
                Paragraph(
                    str(package_title),
                    bold_style,
                ),
            ],
            [
                Paragraph(
                    "Category",
                    normal_style,
                ),
                Paragraph(
                    str(package_category),
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "Weight",
                    normal_style,
                ),
                Paragraph(
                    f"{package_weight} kg",
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "Description",
                    normal_style,
                ),
                Paragraph(
                    str(package_description)[:300],
                    normal_style,
                ),
            ],
        ]

        package_table = Table(
            package_data,
            colWidths=[130, 370],
        )

        package_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        elements.append(package_table)

        # =========================================================
        # PARTICIPANTS
        # =========================================================

        elements.append(
            Paragraph(
                "3. PARTICIPANTS",
                section_style,
            )
        )

        sender_name = cls._get_user_display_name(
            invoice.sender
        )

        traveler_name = cls._get_user_display_name(
            invoice.traveler
        )

        sender_email = (
            getattr(invoice.sender, "email", None)
            or "N/A"
        )

        traveler_email = (
            getattr(invoice.traveler, "email", None)
            or "N/A"
        )

        participant_data = [
            [
                Paragraph(
                    "Sender",
                    normal_style,
                ),
                Paragraph(
                    f"{sender_name} ({sender_email})",
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "Traveler",
                    normal_style,
                ),
                Paragraph(
                    f"{traveler_name} ({traveler_email})",
                    normal_style,
                ),
            ],
        ]

        participant_table = Table(
            participant_data,
            colWidths=[130, 370],
        )

        participant_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        elements.append(participant_table)



        # =========================================================
        # FINANCIAL BREAKDOWN
        # =========================================================

        elements.append(
            Paragraph(
                "4. FINANCIAL BREAKDOWN",
                section_style,
            )
        )

        currency = (
            invoice.currency
            or "USD"
        )

        reward = (
            f"{currency} "
            f"{invoice.reward:.2f}"
        )

        platform_fee = (
            f"{currency} "
            f"{invoice.platform_fee:.2f}"
        )

        total_paid = (
            f"{currency} "
            f"{invoice.total_paid:.2f}"
        )

        financial_data = [
            [
                Paragraph(
                    "Traveler Delivery Reward",
                    normal_style,
                ),
                Paragraph(
                    reward,
                    right_style,
                ),
            ],
            [
                Paragraph(
                    "LuggageLinker Platform Fee",
                    normal_style,
                ),
                Paragraph(
                    platform_fee,
                    right_style,
                ),
            ],
            [
                Paragraph(
                    "<b>Total Amount Paid</b>",
                    bold_style,
                ),
                Paragraph(
                    f"<b>{total_paid}</b>",
                    right_style,
                ),
            ],
        ]

        financial_table = Table(
            financial_data,
            colWidths=[350, 150],
        )

        financial_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "BACKGROUND",
                        (0, 2),
                        (-1, 2),
                        colors.whitesmoke,
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        7,
                    ),
                    (
                        "ALIGN",
                        (1, 0),
                        (1, -1),
                        "RIGHT",
                    ),
                ]
            )
        )

        elements.append(
            financial_table
        )

        # =========================================================
        # PAYMENT DETAILS
        # =========================================================

        elements.append(
            Paragraph(
                "5. PAYMENT DETAILS",
                section_style,
            )
        )

        if hasattr(
            invoice,
            "get_payment_method_display",
        ):
            payment_method = (
                invoice
                .get_payment_method_display()
            )
        else:
            payment_method = (
                invoice.payment_method
            )

        payment_data = [
            [
                Paragraph(
                    "Payment Method",
                    normal_style,
                ),
                Paragraph(
                    str(payment_method),
                    normal_style,
                ),
            ],
            [
                Paragraph(
                    "Transaction ID",
                    normal_style,
                ),
                Paragraph(
                    invoice.transaction_id
                    or "N/A",
                    normal_style,
                ),
            ],
        ]

        payment_table = Table(
            payment_data,
            colWidths=[130, 370],
        )

        payment_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "PADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        elements.append(
            payment_table
        )

        # =========================================================
        # FOOTER
        # =========================================================

        elements.append(
            Spacer(1, 20)
        )

        elements.append(
            Paragraph(
                "Thank you for using LuggageLinker.",
                subtitle_style,
            )
        )

        elements.append(
            Paragraph(
                "support@luggagelinker.com",
                subtitle_style,
            )
        )

        # =========================================================
        # BUILD PDF
        # =========================================================

        document.build(elements)

        buffer.seek(0)

        file_name = (
            f"Invoice_"
            f"{invoice.invoice_number}.pdf"
        )

        invoice.pdf.save(
            file_name,
            ContentFile(
                buffer.read()
            ),
            save=False,
        )

        # ---------------------------------------------------------
        # Save PDF
        # ---------------------------------------------------------

        update_fields = ["pdf"]

        if hasattr(
            invoice,
            "pdf_generated_at",
        ):
            invoice.pdf_generated_at = (
                timezone.now()
            )

            update_fields.append(
                "pdf_generated_at"
            )

        invoice.save(
            update_fields=update_fields
        )

        return invoice