from rest_framework import serializers

from apps.kyc.models import KYC, IDType, KYCStatus
from apps.kyc.models import KYC, KYCStatus

class KYCSerializer(serializers.ModelSerializer):

    class Meta:
        model = KYC

        fields = (
            "id",
            "id_type",
            "id_number",
            "document_front",
            "document_back",
            "selfie",
            "status",
            "rejection_reason",
            "verified_at",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "status",
            "rejection_reason",
            "verified_at",
            "created_at",
            "updated_at",
        )

        extra_kwargs = {
            "id_type": {
                "error_messages": {
                    "required": "ID type is required.",
                    "blank": "ID type cannot be blank.",
                    "invalid_choice": "Please select a valid ID type.",
                }
            },
            "id_number": {
                "error_messages": {
                    "required": "ID number is required.",
                    "blank": "ID number cannot be blank.",
                }
            },
            "document_front": {
                "error_messages": {
                    "required": "Front side of your ID is required."
                }
            },
            "document_back": {
                "error_messages": {
                    "required": "Back side of your ID is required."
                }
            },
            "selfie": {
                "error_messages": {
                    "required": "Selfie is required."
                }
            },
        }
        
    def to_representation(self, instance):
        data = super().to_representation(instance)

        data["document_front"] = (
            instance.document_front.url
            if instance.document_front
            else None
        )

        data["document_back"] = (
            instance.document_back.url
            if instance.document_back
            else None
        )

        data["selfie"] = (
            instance.selfie.url
            if instance.selfie
            else None
        )

        return data
    # -----------------------------------
    # ID NUMBER VALIDATION
    # -----------------------------------

    def validate_id_number(self, value):

        value = value.strip()

        if len(value) < 6:
            raise serializers.ValidationError(
                "ID number is too short."
            )

        queryset = KYC.objects.filter(id_number__iexact=value)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "This ID number is already registered."
            )

        return value

    # -----------------------------------
    # OBJECT VALIDATION
    # -----------------------------------

    def validate(self, attrs):

        request = self.context["request"]
        user = request.user

    # -----------------------------------
    # PROFILE VALIDATION
    # -----------------------------------

        try:
            profile = user.profile
        except Exception:
            raise serializers.ValidationError({
                "detail": "Please create your profile first."
            })

        if not profile.first_name:
            raise serializers.ValidationError({
                "first_name": "Please add your first name in your profile."
            })

        if not profile.last_name:
            raise serializers.ValidationError({
                "last_name": "Please add your last name in your profile."
            })

        if not profile.phone:
            raise serializers.ValidationError({
                "phone": "Please add your phone number in your profile."
            })

        if not profile.date_of_birth:
            raise serializers.ValidationError({
                "date_of_birth": "Please add your date of birth in your profile."
            })


        # One KYC per user
        if not self.instance and KYC.objects.filter(user=user).exists():
            raise serializers.ValidationError({
                "detail": "You have already submitted your KYC."
            })

        id_type = attrs.get(
            "id_type",
            self.instance.id_type if self.instance else None
        )

        document_front = attrs.get(
            "document_front",
            self.instance.document_front if self.instance else None
        )

        document_back = attrs.get(
            "document_back",
            self.instance.document_back if self.instance else None
        )

        selfie = attrs.get(
            "selfie",
            self.instance.selfie if self.instance else None
        )

        if not document_front:
            raise serializers.ValidationError({
                "document_front": "Front document is required."
            })

        if not selfie:
            raise serializers.ValidationError({
                "selfie": "Selfie is required."
            })

        # Passport doesn't require back side
        if id_type != IDType.PASSPORT and not document_back:
            raise serializers.ValidationError({
                "document_back": "Back document is required."
            })

        return attrs

    # -----------------------------------
    # CREATE
    # -----------------------------------

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    # -----------------------------------
    # UPDATE
    # -----------------------------------

    def update(self, instance, validated_data):

        if instance.status == KYCStatus.APPROVED:
            raise serializers.ValidationError({
                "detail": "Approved KYC cannot be modified."
            })

        return super().update(instance, validated_data)







class AdminUserSerializer(serializers.Serializer):
    """Minimal representation of the user for admin readability."""
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField(source="profile.first_name", read_only=True)
    last_name = serializers.CharField(source="profile.last_name", read_only=True)


class AdminKYCDetailSerializer(serializers.ModelSerializer):
    user = AdminUserSerializer(read_only=True)
    verified_by_email = serializers.EmailField(source="verified_by.email", read_only=True)

    class Meta:
        model = KYC
        fields = (
            "id",
            "user",
            "id_type",
            "id_number",
            "document_front",
            "document_back",
            "selfie",
            "status",
            "rejection_reason",
            "verified_at",
            "verified_by_email",
            "created_at",
            "updated_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Safe URL parsing for Cloudinary fields
        data["document_front"] = instance.document_front.url if instance.document_front else None
        data["document_back"] = instance.document_back.url if instance.document_back else None
        data["selfie"] = instance.selfie.url if instance.selfie else None
        return data


class KYCRejectSerializer(serializers.Serializer):
    """Validates that a reason is supplied when rejection occurs."""
    rejection_reason = serializers.CharField(
        required=True, 
        allow_blank=False,
        error_messages={
            "required": "You must provide a reason for rejecting this KYC application.",
            "blank": "Rejection reason cannot be empty."
        }
    )