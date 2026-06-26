from django.shortcuts import render
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.accounts.models import Profile
from apps.accounts.serializers import ProfileSerializer
# Create your views here.

class CreateProfileView(generics.CreateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):

        if Profile.objects.filter(user=request.user).exists():
            return Response(
                {
                    "detail": "Profile already exists."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)

        serializer.save(user=request.user)

        return Response(
            {
                "message": "Profile created successfully.",
                "data": serializer.data
            },
            status=status.HTTP_201_CREATED
        )


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):

        profile, created = Profile.objects.get_or_create(
            user=self.request.user
        )

        return profile

    def get_serializer_context(self):
        return {
            "request": self.request
        }

    def retrieve(self, request, *args, **kwargs):

        serializer = self.get_serializer(self.get_object())

        return Response(
            {
                "message": "Profile fetched successfully.",
                "data": serializer.data
            }
        )

    def update(self, request, *args, **kwargs):

        partial = kwargs.pop("partial", True)

        serializer = self.get_serializer(
            self.get_object(),
            data=request.data,
            partial=partial,
        )

        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response(
            {
                "message": "Profile updated successfully.",
                "data": serializer.data
            }
        )