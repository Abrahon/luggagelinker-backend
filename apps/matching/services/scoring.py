from decimal import Decimal


PICKUP_COUNTRY_SCORE = Decimal("20")
PICKUP_CITY_SCORE = Decimal("10")

DEST_COUNTRY_SCORE = Decimal("20")
DEST_CITY_SCORE = Decimal("10")

DATE_SCORE = Decimal("20")
WEIGHT_SCORE = Decimal("20")

MAX_SCORE = Decimal("100")


def normalize(value):

    if value is None:
        return ""

    return str(value).strip().casefold()


def date_matches(package, trip):

    if not package.pickup_date:
        return False

    if not package.latest_delivery_date:
        return False

    if not trip.departure_date:
        return False

    if not trip.arrival_date:
        return False

    return (
        package.pickup_date <= trip.departure_date
        and
        trip.arrival_date <= package.latest_delivery_date
    )


def weight_matches(package, trip):

    available_weight = (
        trip.available_weight_kg
        if trip.available_weight_kg is not None
        else Decimal("0")
    )

    return available_weight >= package.weight


def calculate_match_score(package, trip):

    score = Decimal("0")

    # Pickup country
    if normalize(package.pickup_country) == normalize(
        trip.from_country
    ):
        score += PICKUP_COUNTRY_SCORE

    # Pickup city
    if normalize(package.pickup_city) == normalize(
        trip.from_city
    ):
        score += PICKUP_CITY_SCORE

    # Destination country
    if normalize(package.destination_country) == normalize(
        trip.to_country
    ):
        score += DEST_COUNTRY_SCORE

    # Destination city
    if normalize(package.destination_city) == normalize(
        trip.to_city
    ):
        score += DEST_CITY_SCORE

    # Dates
    if date_matches(package, trip):
        score += DATE_SCORE

    # Weight
    if weight_matches(package, trip):
        score += WEIGHT_SCORE

    return min(
        score,
        MAX_SCORE,
    )