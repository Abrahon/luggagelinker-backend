import logging
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


class StripeConnectProvider:

    @staticmethod
    def create_connected_account(email: str):
        """
        Creates a new Stripe Express Connected Account for a given user email.
        """
        try:
            account = stripe.Account.create(
                type="express",
                email=email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )
            return account
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe connected account for {email}: {e}")
            raise

    @staticmethod
    def create_account_link(stripe_account_id: str, user):
        """
        Generates a Stripe Express onboarding link redirecting back with user_id.
        """
        try:
            return_url = (
                f"{settings.STRIPE_CONNECT_RETURN_URL}?user_id={user.id}"
            )

            link = stripe.AccountLink.create(
                account=stripe_account_id,
                refresh_url=f"{settings.STRIPE_CONNECT_REFRESH_URL}?user_id={user.id}",
                return_url=return_url,
                type="account_onboarding",
            )

            return link.url

        except stripe.error.StripeError as e:
            logger.error(f"Failed to create account link: {e}")
            raise