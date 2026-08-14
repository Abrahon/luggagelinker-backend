from decimal import Decimal

from apps.packages.models import (
    Package,
    PackageStatus,
    VerificationStatus,
    RiskRule,
)


class PackageService:

    HIGH_RISK_COUNTRIES = {
        "Nigeria",
        "Pakistan",
        "Afghanistan",
        "Iran",
        "Iraq",
        "Syria",
    }

    # ==========================================================
    # PACKAGE RISK EVALUATION
    # ==========================================================

    @staticmethod
    def process_and_evaluate_risk(package: Package) -> Package:

        score = 0

        # --------------------------------------------------
        # 1. Category Risk
        # --------------------------------------------------
        rule = RiskRule.objects.filter(
            category=package.category
        ).first()

        if rule:
            score += rule.base_risk_score

            if (
                package.declared_value >= rule.requires_receipt_above
                and not package.purchase_receipt
            ):
                score += 20

        # --------------------------------------------------
        # 2. Declared Value
        # --------------------------------------------------
        value = package.declared_value

        if value >= Decimal("5000"):
            score += 35
        elif value >= Decimal("2500"):
            score += 30
        elif value >= Decimal("1000"):
            score += 20
        elif value >= Decimal("500"):
            score += 15
        elif value >= Decimal("150"):
            score += 10

        # --------------------------------------------------
        # 3. Reward Amount
        # --------------------------------------------------
        reward = package.reward_amount

        if reward >= Decimal("1000"):
            score += 20
        elif reward >= Decimal("500"):
            score += 15
        elif reward >= Decimal("200"):
            score += 10

        # --------------------------------------------------
        # 4. International Route
        # --------------------------------------------------
        if (
            package.pickup_country.lower().strip()
            != package.destination_country.lower().strip()
        ):
            score += 15

        # --------------------------------------------------
        # 5. High Risk Country
        # --------------------------------------------------
        if package.pickup_country.strip() in PackageService.HIGH_RISK_COUNTRIES:
            score += 15

        # --------------------------------------------------
        # 6. Fragile
        # --------------------------------------------------
        if package.is_fragile:
            score += 5

        # --------------------------------------------------
        # 7. Signature Required
        # --------------------------------------------------
        if package.requires_signature:
            score += 5

        # --------------------------------------------------
        # 8. New User
        # --------------------------------------------------
        profile = getattr(package.sender, "profile", None)

        completed = (
            getattr(profile, "completed_deliveries", 0)
            if profile
            else 0
        )

        if completed == 0:
            score += 10

        # --------------------------------------------------
        # Final Score
        # --------------------------------------------------
        package.risk_score = min(score, 100)

        if package.risk_score >= 50:
            package.verification_status = (
                VerificationStatus.MANUAL_REVIEW
            )
        else:
            package.verification_status = (
                VerificationStatus.AUTO_APPROVED
            )

        package.save(
            update_fields=[
                "risk_score",
                "verification_status",
            ]
        )

        return package

    # ==========================================================
    # FIND PACKAGES COMPATIBLE WITH A SPECIFIC TRIP
    # ==========================================================

    # ==========================================================
    # FIND PACKAGES FOR A SPECIFIC TRIP
    # ==========================================================

    @staticmethod
    def find_packages_for_trip(trip, sender):
        """
        Return only the sender's packages that are compatible
        with the selected trip.

        Used when the sender clicks:
            "Booking Request"

        Matching rules:
            - Package belongs to sender
            - Package is published
            - Package is active
            - Route matches trip
            - Pickup date is before/on trip departure
            - Delivery deadline is after/on trip arrival
            - Package weight fits available capacity
        """

        return Package.objects.filter(
            sender=sender,
            status=PackageStatus.PUBLISHED,
            is_active=True,

            # ==================================================
            # ROUTE
            # ==================================================

            pickup_country__iexact=trip.from_country,
            pickup_city__iexact=trip.from_city,

            destination_country__iexact=trip.to_country,
            destination_city__iexact=trip.to_city,

            # ==================================================
            # DATE
            # ==================================================

            pickup_date__lte=trip.departure_date,
            latest_delivery_date__gte=trip.arrival_date,

            # ==================================================
            # CAPACITY
            # ==================================================

            weight__lte=trip.available_weight_kg,
        )


    # ==========================================================
    # VALIDATE ONE PACKAGE AGAINST ONE SPECIFIC TRIP
    # ==========================================================

    @staticmethod
    def validate_package_for_trip(package, trip, sender):
        """
        Final backend validation before creating a booking.

        The frontend may show only matching packages, but we
        MUST validate again here because the frontend cannot
        be trusted.

        Returns:
            (True, None)
            OR
            (False, "error message")
        """

        # ======================================================
        # 1. PACKAGE OWNER
        # ======================================================

        if package.sender_id != sender.id:
            return False, (
                "This package does not belong to you."
            )

        # ======================================================
        # 2. PACKAGE STATUS
        # ======================================================

        if package.status != PackageStatus.PUBLISHED:
            return False, (
                "Package must be published."
            )

        # ======================================================
        # 3. PACKAGE ACTIVE
        # ======================================================

        if not package.is_active:
            return False, (
                "Package is inactive."
            )

        # ======================================================
        # 4. ROUTE VALIDATION
        # ======================================================

        if (
            package.pickup_country.strip().casefold()
            != trip.from_country.strip().casefold()
        ):
            return False, (
                "Package pickup country does not match the trip."
            )

        if (
            package.pickup_city.strip().casefold()
            != trip.from_city.strip().casefold()
        ):
            return False, (
                "Package pickup city does not match the trip."
            )

        if (
            package.destination_country.strip().casefold()
            != trip.to_country.strip().casefold()
        ):
            return False, (
                "Package destination country does not match the trip."
            )

        if (
            package.destination_city.strip().casefold()
            != trip.to_city.strip().casefold()
        ):
            return False, (
                "Package destination city does not match the trip."
            )

        # ======================================================
        # 5. PICKUP DATE
        # ======================================================

        if (
            package.pickup_date
            and trip.departure_date
            and package.pickup_date > trip.departure_date
        ):
            return False, (
                "Package pickup date is after the trip departure date."
            )

        # ======================================================
        # 6. DELIVERY DATE
        # ======================================================

        if (
            package.latest_delivery_date
            and trip.arrival_date
            and package.latest_delivery_date < trip.arrival_date
        ):
            return False, (
                "Package delivery deadline is before the trip arrival date."
            )

        # ======================================================
        # 7. WEIGHT / CAPACITY
        # ======================================================

        if (
            package.weight > trip.available_weight_kg
        ):
            return False, (
                f"Package weight ({package.weight}kg) exceeds "
                f"available trip capacity ({trip.available_weight_kg}kg)."
            )

        # ======================================================
        # EVERYTHING MATCHES
        # ======================================================

        return True, None

    
    @staticmethod
    def publish_package(package):

        if (
            package.verification_status
            in [
                VerificationStatus.AUTO_APPROVED,
                VerificationStatus.VERIFIED,
            ]
            and package.is_public
        ):
            package.status = PackageStatus.PUBLISHED
            package.is_active = True
            package.save(
                update_fields=[
                    "status",
                    "is_active",
                ]
            )
            return True

        return False

    @staticmethod
    def review_package(package: Package, approve: bool) -> Package:
        """
        Admin approves or rejects a package after manual review.
        """

        if package.verification_status not in [
            VerificationStatus.MANUAL_REVIEW,
            VerificationStatus.AUTO_APPROVED,
        ]:
            raise ValueError(
                "This package cannot be reviewed."
            )

        if approve:
            package.verification_status = VerificationStatus.VERIFIED
            package.status = PackageStatus.PUBLISHED
            package.is_active = True
            package.is_public = True

        else:
            package.verification_status = VerificationStatus.REJECTED
            package.status = PackageStatus.CANCELLED
            package.is_active = False
            package.is_public = False

        package.save(
            update_fields=[
                "verification_status",
                "status",
                "is_active",
                "is_public",
                "updated_at",
            ]
        )

        return package