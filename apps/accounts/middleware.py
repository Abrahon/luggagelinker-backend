from django.http import JsonResponse

from apps.reviews.models import UserModerationProfile


class ModerationMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        user = request.user

        if user.is_authenticated:

            try:
                moderation = user.moderation_profile

                moderation.check_suspension_status()

                if moderation.is_banned:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Your account has been permanently banned. Please contact support.",
                        },
                        status=403,
                    )

                if moderation.is_suspended:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": f"Your account has been suspended until {moderation.suspended_until}.",
                        },
                        status=403,
                    )

            except UserModerationProfile.DoesNotExist:
                pass

        return self.get_response(request)