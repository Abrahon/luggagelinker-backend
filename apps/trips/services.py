from django.utils import timezone

from .models import TripStatus


class TripStatusService:

    @staticmethod
    def sync_status(trip):
        today = timezone.localdate()

        # Never automatically change cancelled trips
        if trip.status == TripStatus.CANCELLED:
            return trip

        if today < trip.departure_date:
            new_status = TripStatus.PLANNED

        elif trip.departure_date <= today <= trip.arrival_date:
            new_status = TripStatus.ACTIVE

        else:
            new_status = TripStatus.COMPLETED

        if trip.status != new_status:
            trip.status = new_status
            trip.save(update_fields=["status"])

        return trip