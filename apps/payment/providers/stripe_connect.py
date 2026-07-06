import logging
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


class StripeConnectProvider:

    @staticmethod
    def create_connected_account(email: str) -> stripe.Account:
        """
        Creates a Stripe Express Connected Account for a user.
        """
        try:
            account = stripe.Account.create(
                type="express",
                country="US",
                email=email,
                capabilities={
                    "transfers": {"requested": True},
                },
            )
            return account
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe Express account for {email}: {str(e)}")
            raise e

    @staticmethod
    def create_account_link(account_id: str) -> str:
        """
        Generates a secure, temporary onboarding flow redirection URL.
        """
        try:
            link = stripe.AccountLink.create(
                account=account_id,
                refresh_url=settings.STRIPE_CONNECT_REFRESH_URL,
                return_url=settings.STRIPE_CONNECT_RETURN_URL,
                type="account_onboarding",
            )
            return link.url
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe Account Link for {account_id}: {str(e)}")
            raise e