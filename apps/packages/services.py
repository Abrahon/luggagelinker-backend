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
        if (
            package.pickup_country.strip()
            in PackageService.HIGH_RISK_COUNTRIES
        ):
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

        completed = getattr(
            profile,
            "completed_deliveries",
            0,
        ) if profile else 0

        if completed == 0:
            score += 10

        # --------------------------------------------------
        # Final Score
        # --------------------------------------------------
        package.risk_score = min(score, 100)

        # < 50 = Auto Approve
        # >= 50 = Manual Review
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