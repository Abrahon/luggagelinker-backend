from django.shortcuts import render
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import generics, status
from apps.accounts.models import User, OTP
# from apps.subscriptions.models import Subscription
from apps.accounts.models import User, OTP
from.serializers import SignupSerializer
# ✅ OTP service functions
from shared.services.otp_service import (
    create_otp,
    verify_otp,
    send_otp_email
)

import logging

logger = logging.getLogger(__name__)



class SignupView(generics.GenericAPIView):

    serializer_class = SignupSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        email = data["email"].strip().lower()

        with transaction.atomic():

            # ----------------------------
            # CHECK EXISTING USER
            # ----------------------------
            existing_user = User.objects.filter(email__iexact=email).first()

            if existing_user and existing_user.is_verified:
                return Response(
                    {"detail": "User already exists."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if existing_user:
                existing_user.delete()

            # ----------------------------
            # CREATE USER
            # ----------------------------
            user = User.objects.create_user(
                email=email,
                password=data["password"],
                role=data["role"],
                is_active=True,
                is_verified=False,
            )

            # ----------------------------
            # CREATE OTP (SERVICE LAYER ONLY)
            # ----------------------------
            otp_obj = create_otp(
                user=user,
                email=email,
                purpose="email_verification",
                expiry_minutes=5
            )

        # ----------------------------
        # SEND EMAIL (FIXED CALL)
        # ----------------------------
        send_otp_email(
            to_email=email,
            otp_code=otp_obj.code,
            name=email
        )

        return Response(
            {"detail": "OTP sent to your email. Please verify account."},
            status=status.HTTP_201_CREATED,
        )



class VerifyOTPView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        email = str(request.data.get("email") or "").strip().lower()
        otp_code = str(request.data.get("otp") or "").strip()

        if not email or not otp_code:
            return Response(
                {"detail": "Email and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():

                user = User.objects.filter(email__iexact=email).first()

                if not user:
                    return Response(
                        {"detail": "User not found."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                success, message = verify_otp(
                    user=user,
                    code=otp_code,
                    purpose="email_verification"
                )

                if not success:
                    return Response(
                        {"detail": message},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # mark verified
                user.is_verified = True
                user.save(update_fields=["is_verified"])

        except Exception:
            logger.exception("OTP verification failed")
            return Response(
                {"detail": "Verification failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # JWT
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "detail": "Email verified successfully.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "is_verified": user.is_verified,
                },
            },
            status=status.HTTP_200_OK,
        )