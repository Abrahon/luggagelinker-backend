from decimal import Decimal
from apps.packages.models import Package, PackageStatus, VerificationStatus, RiskRule


class PackageService:
    """
    Dedicated Service Layer orchestrating risk evaluation, dynamic scoring pipelines,
    automated publication rules, and explicit administrative oversight transitions.
    """

    @staticmethod
    def process_and_evaluate_risk(package: Package) -> Package:
        """
        Runs automated risk assessments against configured rules and user traits.
        Updates verification state without deciding marketplace publication workflow.
        """
        score = 0

        # 1. Fetch Dynamic Category Weight from Admin Risk Rules database
        rule = RiskRule.objects.filter(category=package.category).first()
        if rule:
            score += rule.base_risk_score
            # Check threshold requirement rules
            if package.declared_value >= rule.requires_receipt_above and not package.purchase_receipt:
                score += 20

        # 2. Declared Value Tier Assessment
        if package.declared_value > Decimal("500.00"):
            score += 20
        elif package.declared_value > Decimal("150.00"):
            score += 10

        # 3. Route Evaluation Boundary (International vs Domestic)
        if package.pickup_country.lower().strip() != package.destination_country.lower().strip():
            score += 15

        # 4. Fast User Profile Evaluation Look-up (No heavy database cross-table scans)
        user_profile = getattr(package.sender, 'profile', None)
        completed_count = getattr(user_profile, 'completed_shipments', 0) if user_profile else 0
        if completed_count == 0:
            score += 15

        # Commit score calculations onto object instance state
        package.risk_score = min(score, 100)
        
        if package.risk_score >= 70:
            package.verification_status = VerificationStatus.MANUAL_REVIEW
        else:
            package.verification_status = VerificationStatus.AUTO_APPROVED

        package.save()
        return package

    @staticmethod
    def publish_package(package: Package) -> bool:
        """
        Encapsulates explicit listing publication criteria independently.
        Returns True if criteria met and updated, False otherwise.
        """
        allowed_states = [VerificationStatus.AUTO_APPROVED, VerificationStatus.VERIFIED]
        
        if package.verification_status in allowed_states and package.is_public:
            package.status = PackageStatus.PUBLISHED
            package.save(update_fields=['status'])
            return True
            
        return False

    @staticmethod
    def review_package(package: Package, approve: bool) -> Package:
        """
        Handles human administrative oversight overrides on packages flagged for manual review.
        Triggers publication if approved; marks listing as cancelled if rejected.
        """
        if package.verification_status != VerificationStatus.MANUAL_REVIEW:
            raise ValueError("Package is not awaiting manual review.")

        if approve:
            package.verification_status = VerificationStatus.VERIFIED
            package.save(update_fields=["verification_status"])
            
            # Chain the automated publishing execution check down the line
            PackageService.publish_package(package)
        else:
            package.verification_status = VerificationStatus.REJECTED
            package.status = PackageStatus.CANCELLED
            package.save(update_fields=[
                "verification_status",
                "status",
            ])

        return package