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
from django.utils import timezone
from shared.utils.email import generate_otp, send_otp_email,get_tokens_for_user
import threading
import logging
from django.core import signing
import uuid
from django.core.signing import BadSignature, SignatureExpired
from .serializers import LoginSerializer

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

            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                if existing_user.is_active:
                    return Response(
                        {"detail": "User with this email already exists."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    existing_user.delete()

            OTP.objects.filter(email__iexact=email).delete()

            otp_code = generate_otp()

            # ✅ CREATE USER
            user = User.objects.create_user(
                email=email,
                password=data["password"],
                role=data["role"],
                is_active=False,
            )

            # ✅ GET FREE PLAN
            # free_plan = Plan.objects.filter(
            #     plan_type=Plan.PLAN_FREE,
            #     is_active=True
            # ).first()

            # if not free_plan:
            #     raise Exception("Free plan not configured in database")

            # ✅ CREATE SUBSCRIPTION
            # Subscription.objects.create(
            #     user=user,
            #     plan=free_plan,
            #     billing_cycle=Subscription.BILLING_MONTHLY,
            #     status=Subscription.STATUS_ACTIVE,
            #     started_at=timezone.now(),
            #     expires_at=timezone.now() + timedelta(days=365 * 10),  # long free access
            #     auto_renew=False,
            # )

            # OTP create
            OTP.objects.create(
                user=user,
                email=email,
                code=otp_code,
            )

        # WhatsApp preference
        # if user.phone:
        #     try:
        #         UserWhatsAppPreference.objects.get_or_create(
        #             user=user,
        #             defaults={
        #                 "phone": normalize_whatsapp_number(user.phone),
        #                 "is_verified": False,
        #                 "is_enabled": False,
        #             },
        #         )
        #     except Exception as exc:
        #         print("WhatsApp preference create failed:", str(exc))

        # send OTP async
        threading.Thread(
            target=send_otp_email,
            args=(email, otp_code),
            daemon=True,
        ).start()

        return Response(
            {"detail": f"Verification OTP sent to {email}."},
            status=status.HTTP_200_OK,
        )
    


# verify email
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email") or "").strip().lower()
        otp = str(request.data.get("otp") or "").strip()

        if not email or not otp:
            return Response(
                {"detail": "Email and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info("VerifyOTPView called | email=%s", email)

        try:
            with transaction.atomic():
                otp_obj = (
                    OTP.objects.select_for_update()
                    .filter(email__iexact=email, code=otp)
                    .order_by("-created_at")
                    .first()
                )

                if not otp_obj:
                    return Response(
                        {"detail": "Invalid OTP."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if otp_obj.is_expired():
                    otp_obj.delete()
                    return Response(
                        {"detail": "OTP expired."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    return Response(
                        {"detail": "User not found. Please register again."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if not user.is_active:
                    user.is_active = True
                    user.save(update_fields=['is_active'])

                OTP.objects.filter(email__iexact=email).delete()

        except Exception:
            logger.exception("Unexpected error during OTP verification")
            return Response(
                {"detail": "Something went wrong while verifying OTP."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # =========================
        # FIX: FETCH SUBSCRIPTION PLAN
        # =========================
        # subscription = (
        #     Subscription.objects
        #     .select_related("plan")
        #     .filter(user=user)
        #     .first()
        # )

        # plan_type = (
        #     subscription.plan.plan_type
        #     if subscription and subscription.plan
        #     else None
        # )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "detail": "OTP verified successfully.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    # "name": user.name,
                    "role": user.role,
                    # "plan_type": plan_type,
                },
            },
            status=status.HTTP_201_CREATED,
        )



class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {
                        "success": False,
                        "message": "Login failed.",
                        "errors": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            auth_user = serializer.validated_data["user"]

            try:
                # user = User.objects.select_related("profile").get(id=auth_user.id)
                user = auth_user
            except User.DoesNotExist:
                return Response(
                    {
                        "success": False,
                        "message": "User not found.",
                        "errors": {"detail": ["User does not exist."]},
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
  
            if not user.is_active:
                return Response(
                    {
                        "success": False,
                        "message": "Please verify your email first.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )


            user_data = LoginSerializer(user, context={"request": request}).data

            # NORMAL LOGIN (ALL USERS INCLUDING SUPER ADMIN)
            try:
                tokens = get_tokens_for_user(user)
                User.objects.filter(id=user.id).update(last_login=timezone.now())

                return Response(
                    {
                        "success": True,
                        "message": "Login successful.",
                        "token": tokens,
                        "user": user_data,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {
                        "success": False,
                        "message": "Token generation failed.",
                        "errors": {"detail": str(e)},
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            logger.exception(e)
            return Response(
                {
                    "success": False,
                    "message": "Something went wrong while sending the invitation.",
                    "errors": {"detail": str(e)},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# resend views
# resend otp
class ResendOTPView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email") or "").strip().lower()

        if not email:
            return Response({"detail": "Email is required."}, status=400)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "User not found."}, status=404)

        OTP.objects.filter(user=user).delete()

        otp_code = generate_otp()
        OTP.objects.create(user=user, email=user.email, code=str(otp_code))

        send_otp_email(user.email, str(otp_code))

        return Response({"detail": "OTP resent successfully"}, status=200)



# forget pass
# FORGOT PASSWORD - SEND OTP
class ForgotPasswordOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        user = User.objects.filter(email=email).first()

        if not user:
            return Response({"detail": "User not found"}, status=404)

        OTP.objects.filter(user=user).delete()

        otp_code = generate_otp()
        OTP.objects.create(user=user, code=otp_code)

        send_otp_email(email, otp_code)

        return Response({"detail": "OTP sent"})





class VerifyForgotOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"detail": "Email and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        otp_obj = OTP.objects.filter(user=user, code=otp).order_by("-created_at").first()

        if not otp_obj:
            return Response(
                {"detail": "Invalid OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_obj.is_expired():
            otp_obj.delete()
            return Response(
                {"detail": "OTP expired."},
                status=status.HTTP_400_BAD_REQUEST
            )


        reset_token = signing.dumps(
            {
                "user_id": str(user.id),
                "email": user.email,
                "purpose": "password_reset",
            },
            salt="password-reset",
        )
        print("received token:", repr(reset_token))
        otp_obj.delete()

        return Response(
            {
                "detail": "OTP verified successfully.",
                "reset_token": reset_token,
            },
            status=status.HTTP_200_OK
        )




class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("reset_token")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not token or not new_password or not confirm_password:
            return Response(
                {"detail": "reset_token, new_password and confirm_password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                {"detail": "Passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = signing.loads(token, salt="password-reset", max_age=600)
        except SignatureExpired:
            return Response(
                {"detail": "Reset token expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except BadSignature:
            return Response(
                {"detail": "Invalid reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = uuid.UUID(payload["user_id"])
            email = payload["email"]
        except (KeyError, ValueError, TypeError):
            return Response(
                {"detail": "Invalid token payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(id=user_id, email__iexact=email).first()
        if not user:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
       # New password cannot be the same as the current password
        if user.check_password(new_password):
            return Response(
                {
                    "detail": "Your new password cannot be the same as your current password."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


        user.set_password(new_password)
        user.save()

        return Response(
            {"detail": "Password reset successful."},
            status=status.HTTP_200_OK,
        )




