from decimal import Decimal

from django.db import transaction

from apps.packages.models import (
    Package,
    PackageStatus,
    VerificationStatus,
    RiskRule,
    PackageCategory,
)

from apps.matching.services.package_matching import (
    run_package_matching,
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
        # 1. CATEGORY RISK
        # --------------------------------------------------

        rule = RiskRule.objects.filter(
            category=package.category
        ).first()

        if rule:
            score += rule.base_risk_score

            if (
                rule.requires_receipt
                and not package.purchase_receipt
            ):
                score += 20

        # --------------------------------------------------
        # 2. INTERNATIONAL ROUTE
        # --------------------------------------------------

        if (
            package.pickup_country
            and package.destination_country
            and package.pickup_country.lower().strip()
            != package.destination_country.lower().strip()
        ):
            score += 15

        # --------------------------------------------------
        # 3. HIGH RISK COUNTRY
        # --------------------------------------------------

        high_risk_countries = {
            country.lower()
            for country in PackageService.HIGH_RISK_COUNTRIES
        }

        if (
            package.pickup_country
            and package.pickup_country.strip().lower()
            in high_risk_countries
        ):
            score += 15

        if (
            package.destination_country
            and package.destination_country.strip().lower()
            in high_risk_countries
        ):
            score += 15

        # --------------------------------------------------
        # 4. FRAGILE PACKAGE
        # --------------------------------------------------

        if package.is_fragile:
            score += 5

        # --------------------------------------------------
        # 5. SIGNATURE REQUIRED
        # --------------------------------------------------

        if package.requires_signature:
            score += 5

        # --------------------------------------------------
        # 6. MISSING PURCHASE RECEIPT
        # --------------------------------------------------

        if (
            package.category
            in [
                PackageCategory.ELECTRONICS,
                PackageCategory.MEDICINE,
                PackageCategory.COSMETICS,
                PackageCategory.FOOD,
            ]
            and not package.purchase_receipt
        ):
            score += 10

        # --------------------------------------------------
        # 7. ELECTRONICS SERIAL / IMEI
        # --------------------------------------------------

        if package.category == PackageCategory.ELECTRONICS:

            if (
                not package.serial_number
                and not package.imei
            ):
                score += 15

        # --------------------------------------------------
        # 8. LEGAL DECLARATION
        # --------------------------------------------------

        if not package.declared_as_legal:
            score += 30

        # --------------------------------------------------
        # 9. TERMS ACCEPTANCE
        # --------------------------------------------------

        if not package.terms_accepted:
            score += 20

        # --------------------------------------------------
        # 10. NEW USER
        # --------------------------------------------------

        profile = getattr(
            package.sender,
            "profile",
            None,
        )

        completed = (
            getattr(
                profile,
                "completed_deliveries",
                0,
            )
            if profile
            else 0
        )

        if completed == 0:
            score += 10

        elif completed < 3:
            score += 5

        # --------------------------------------------------
        # 11. WEIGHT RISK
        # --------------------------------------------------

        if package.weight >= Decimal("50"):
            score += 15

        elif package.weight >= Decimal("25"):
            score += 10

        elif package.weight >= Decimal("10"):
            score += 5

        # --------------------------------------------------
        # FINAL SCORE
        # --------------------------------------------------

        package.risk_score = min(
            score,
            100,
        )

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
    # FIND PACKAGES FOR A SPECIFIC TRIP
    # ==========================================================

    @staticmethod
    def find_packages_for_trip(
        trip,
        sender,
    ):
        """
        Return only the authenticated sender's packages
        that are compatible with the selected trip.
        """

        return Package.objects.filter(
            sender=sender,

            # --------------------------------------------------
            # PACKAGE ELIGIBILITY
            # --------------------------------------------------

            status=PackageStatus.PUBLISHED,
            is_active=True,
            is_public=True,

            # --------------------------------------------------
            # ROUTE
            # --------------------------------------------------

            pickup_country__iexact=trip.from_country,
            pickup_city__iexact=trip.from_city,

            destination_country__iexact=trip.to_country,
            destination_city__iexact=trip.to_city,

            # --------------------------------------------------
            # DATE
            # --------------------------------------------------

            pickup_date__lte=trip.departure_date,
            latest_delivery_date__gte=trip.arrival_date,

            # --------------------------------------------------
            # CAPACITY
            # --------------------------------------------------

            weight__lte=trip.available_weight_kg,
        )

    # ==========================================================
    # VALIDATE PACKAGE FOR TRIP
    # ==========================================================

    @staticmethod
    def validate_package_for_trip(
        package,
        trip,
        sender,
    ):
        """
        Final backend validation before creating a booking.
        """

        # --------------------------------------------------
        # 1. PACKAGE OWNER
        # --------------------------------------------------

        if package.sender_id != sender.id:

            return False, (
                "This package does not belong to you."
            )

        # --------------------------------------------------
        # 2. PACKAGE STATUS
        # --------------------------------------------------

        if package.status != PackageStatus.PUBLISHED:

            return False, (
                "Package must be published."
            )

        # --------------------------------------------------
        # 3. PACKAGE ACTIVE
        # --------------------------------------------------

        if not package.is_active:

            return False, (
                "Package is inactive."
            )

        # --------------------------------------------------
        # 4. PACKAGE PUBLIC
        # --------------------------------------------------

        if not package.is_public:

            return False, (
                "Package is not publicly available."
            )

        # --------------------------------------------------
        # 5. PREVENT OWN TRIP
        # --------------------------------------------------

        if trip.traveler_id == package.sender_id:

            return False, (
                "You cannot send a booking request "
                "to your own trip."
            )

        # --------------------------------------------------
        # 6. ROUTE VALIDATION
        # --------------------------------------------------

        if (
            package.pickup_country.strip().casefold()
            != trip.from_country.strip().casefold()
        ):

            return False, (
                "Package pickup country does not "
                "match the trip."
            )

        if (
            package.pickup_city.strip().casefold()
            != trip.from_city.strip().casefold()
        ):

            return False, (
                "Package pickup city does not "
                "match the trip."
            )

        if (
            package.destination_country.strip().casefold()
            != trip.to_country.strip().casefold()
        ):

            return False, (
                "Package destination country does not "
                "match the trip."
            )

        if (
            package.destination_city.strip().casefold()
            != trip.to_city.strip().casefold()
        ):

            return False, (
                "Package destination city does not "
                "match the trip."
            )

        # --------------------------------------------------
        # 7. PICKUP DATE
        # --------------------------------------------------

        if (
            package.pickup_date
            and trip.departure_date
            and package.pickup_date
            > trip.departure_date
        ):

            return False, (
                "Package pickup date is after "
                "the trip departure date."
            )

        # --------------------------------------------------
        # 8. DELIVERY DATE
        # --------------------------------------------------

        if (
            package.latest_delivery_date
            and trip.arrival_date
            and package.latest_delivery_date
            < trip.arrival_date
        ):

            return False, (
                "Package delivery deadline is before "
                "the trip arrival date."
            )

        # --------------------------------------------------
        # 9. WEIGHT / CAPACITY
        # --------------------------------------------------

        available_weight = (
            trip.available_weight_kg
            if trip.available_weight_kg is not None
            else Decimal("0")
        )

        if package.weight > available_weight:

            return False, (
                f"Package weight ({package.weight}kg) "
                f"exceeds available trip capacity "
                f"({available_weight}kg)."
            )

        # --------------------------------------------------
        # EVERYTHING MATCHES
        # --------------------------------------------------

        return True, None

    # ==========================================================
    # PUBLISH PACKAGE
    # ==========================================================

    @staticmethod
    @transaction.atomic
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
                    "updated_at",
                ]
            )

            # --------------------------------------------------
            # CREATE MATCHES
            # --------------------------------------------------

            run_package_matching(package)

            return True

        return False

    # ==========================================================
    # ADMIN REVIEW
    # ==========================================================

    @staticmethod
    @transaction.atomic
    def review_package(
        package: Package,
        approve: bool,
    ) -> Package:
        """
        Admin approves or rejects a package.

        APPROVE:
            VERIFIED
            PUBLISHED
            ACTIVE
            PUBLIC
            CREATE MATCHES

        REJECT:
            REJECTED
            CANCELLED
            INACTIVE
            NOT PUBLIC
        """

        # --------------------------------------------------
        # VALID REVIEW STATUS
        # --------------------------------------------------

        if package.verification_status not in [
            VerificationStatus.MANUAL_REVIEW,
            VerificationStatus.AUTO_APPROVED,
        ]:

            raise ValueError(
                "This package cannot be reviewed."
            )

        # ==================================================
        # APPROVE
        # ==================================================

        if approve:

            package.verification_status = (
                VerificationStatus.VERIFIED
            )

            package.status = (
                PackageStatus.PUBLISHED
            )

            package.is_active = True
            package.is_public = True

            package.save(
                update_fields=[
                    "verification_status",
                    "status",
                    "is_active",
                    "is_public",
                    "updated_at",
                ]
            )

            # ==================================================
            # IMPORTANT
            # ==================================================
            # Package is now PUBLISHED.
            # Therefore matching can safely run.
            # ==================================================

            matches = run_package_matching(
                package
            )

            logger_message = (
                f"Package approved and published. "
                f"Package={package.id}, "
                f"Matches created={len(matches)}"
            )

            # Optional logging
            import logging

            logging.getLogger(
                __name__
            ).info(logger_message)

        # ==================================================
        # REJECT
        # ==================================================

        else:

            package.verification_status = (
                VerificationStatus.REJECTED
            )

            package.status = (
                PackageStatus.CANCELLED
            )

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