import logging
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


class StripeConnectProvider:

    @staticmethod
    @classmethod
    def create_account_link(cls, stripe_account_id, user):  
        try:
            return_url_with_context = f"{settings.STRIPE_CONNECT_RETURN_URL}?user_id={user.id}"

            link = stripe.AccountLink.create(
                account=stripe_account_id,
                refresh_url=settings.STRIPE_CONNECT_REFRESH_URL,
                return_url=return_url_with_context,  
                type="account_onboarding",
            )
            return link.url
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe Account Link for {stripe_account_id}: {str(e)}")
            raise e
        
        
    @staticmethod
    def retrieve_account_status(account_id: str) -> stripe.Account:
        """
        Fetches live capability flags directly from the Stripe Connect API engine.
        """
        try:
            return stripe.Account.retrieve(account_id)
        except stripe.error.StripeError as e:
            logger.error(f"Failed to sync status for Stripe account {account_id}: {str(e)}")
            raise e