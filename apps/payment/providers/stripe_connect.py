import logging
import stripe
from django.conf import settings
from types import SimpleNamespace
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

    @staticmethod
    def retrieve_account_status(stripe_account_id: str):
        """
        Retrieves real-time verification and capabilities status for a Stripe Connected Account.
        """
        try:
            account = stripe.Account.retrieve(stripe_account_id)
            
            is_fully_verified = (
                account.details_submitted
                and account.charges_enabled
                and account.payouts_enabled
            )

            # Returning SimpleNamespace allows dot notation (live_account_data.payouts_enabled)
            return SimpleNamespace(
                stripe_account_id=account.id,
                payouts_enabled=account.payouts_enabled,
                charges_enabled=account.charges_enabled,
                details_submitted=account.details_submitted,
                country=account.country,
                default_currency=account.default_currency,
                account_status="ACTIVE" if is_fully_verified else "PENDING",
                raw_account=account,
            )
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve Stripe account status for {stripe_account_id}: {e}")
            raise