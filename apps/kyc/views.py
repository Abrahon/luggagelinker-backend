from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.kyc.models import KYC
from apps.kyc.serializers import KYCSerializer
from rest_framework import generics
from shared.utils.ocr import extract_text_from_url
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.kyc.models import KYC, KYCStatus
from rest_framework.exceptions import ValidationError
from apps.kyc.models import KYC



class KYCCreateView(generics.CreateAPIView):
    """
    Submit KYC Initial payload
    POST /api/kyc/
    """
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        if KYC.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "You have already submitted your KYC."})

        # Step 1: Write safely to database once
        kyc = serializer.save()

        # Step 2: Isolation protection wrapper for third party operations
        if kyc.document_front:
            try:
                text = extract_text_from_url(kyc.document_front.url)
                # Production roadmap recommendation: 
                # Fire an async Celery task instead of locking the HTTP thread here!
                print("\n========== OCR RESULT ==========")
                print(text)
                print("================================\n")
            except Exception as e:
                # Log error telemetry here safely without crashing user experience
                print(f"OCR Processing failed gracefully: {str(e)}")





class MyKYCView(generics.RetrieveUpdateAPIView):
    """
    Manage user context KYC asset instances
    GET /api/kyc/me/
    PATCH /api/kyc/me/
    """
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Clean execution flow instead of an unhandled HTTP 500 error
        return get_object_or_404(KYC, user=self.request.user)

    def perform_update(self, serializer):
        kyc = self.get_object()
        if kyc.status == KYCStatus.APPROVED:
            raise ValidationError({"detail": "Approved KYC records cannot be modified."})
        serializer.save()