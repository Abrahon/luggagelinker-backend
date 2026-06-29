from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.kyc.models import KYC
from apps.kyc.serializers import KYCSerializer
from rest_framework import generics
from shared.utils.ocr import extract_text_from_url

from rest_framework.exceptions import ValidationError
from apps.kyc.models import KYC



class KYCCreateView(generics.CreateAPIView):
    """
    Submit KYC
    POST /api/kyc/
    """

    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return KYC.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        if KYC.objects.filter(user=self.request.user).exists():
            raise ValidationError({
                "detail": "You have already submitted your KYC."
            })

        # Save KYC
        kyc = serializer.save(user=self.request.user)
 
        # Run OCR on the front document
        kyc = serializer.save(user=self.request.user)

        text = extract_text_from_url(kyc.document_front.url)

        print("\n========== OCR RESULT ==========")
        print(text)
        print("================================\n")





class MyKYCView(generics.RetrieveUpdateAPIView):
    """
    GET /api/kyc/me/
    PATCH /api/kyc/me/
    """

    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return KYC.objects.get(user=self.request.user)

    def perform_update(self, serializer):

        kyc = self.get_object()

        if kyc.status == KYC.Status.APPROVED:
            raise ValidationError({
                "detail": "Approved KYC cannot be modified."
            })

        serializer.save()