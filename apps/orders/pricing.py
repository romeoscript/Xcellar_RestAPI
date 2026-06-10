"""
Server-side delivery pricing.

Fees must never be trusted from the client. Every order's delivery_fee,
service_charge, insurance_fee and total_amount are computed here from the
real distance between pickup and dropoff plus parcel attributes. The same
function backs both the /orders/quote/ preview endpoint and order creation,
so the price the user is shown is exactly the price that gets charged.

Pricing constants can be overridden via Django settings without code changes.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import asin, cos, radians, sin, sqrt

from django.conf import settings
from django.utils import timezone


def _setting(name, default):
    return Decimal(str(getattr(settings, name, default)))


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two lat/lng points, in kilometres."""
    lat1, lng1, lat2, lng2 = (float(lat1), float(lng1), float(lat2), float(lng2))
    r = 6371.0  # Earth radius (km)
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    )
    return r * 2 * asin(sqrt(a))


def _money(value):
    """Round a Decimal to 2 dp using bankers-safe half-up rounding."""
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def quote_delivery(
    pickup_latitude,
    pickup_longitude,
    dropoff_latitude,
    dropoff_longitude,
    parcel_weight_kg=None,
    parcel_financial_worth=None,
):
    """
    Compute an authoritative delivery quote.

    Returns a dict with Decimal money fields plus distance/ETA metadata:
        distance_km, delivery_fee, service_charge, insurance_fee,
        total_amount, estimated_minutes, estimated_delivery_time
    """
    # Tunable constants (overridable via settings).
    base_fare = _setting('PRICING_BASE_FARE', '700')          # flag-down fee
    per_km = _setting('PRICING_PER_KM', '120')                # distance rate
    free_weight_kg = _setting('PRICING_FREE_WEIGHT_KG', '5')  # weight included
    per_extra_kg = _setting('PRICING_PER_EXTRA_KG', '50')     # surcharge / kg
    service_rate = _setting('PRICING_SERVICE_RATE', '0.12')   # platform fee %
    insurance_rate = _setting('PRICING_INSURANCE_RATE', '0.015')  # of worth
    avg_speed_kmh = _setting('PRICING_AVG_SPEED_KMH', '25')   # for ETA
    handling_minutes = _setting('PRICING_HANDLING_MINUTES', '15')

    distance_km = Decimal(str(haversine_km(
        pickup_latitude, pickup_longitude,
        dropoff_latitude, dropoff_longitude,
    )))

    # Distance component.
    delivery_fee = base_fare + (per_km * distance_km)

    # Weight surcharge for anything over the included allowance.
    weight = Decimal(str(parcel_weight_kg or 0))
    if weight > free_weight_kg:
        delivery_fee += per_extra_kg * (weight - free_weight_kg)

    delivery_fee = _money(delivery_fee)
    service_charge = _money(delivery_fee * service_rate)

    worth = Decimal(str(parcel_financial_worth or 0))
    insurance_fee = _money(worth * insurance_rate) if worth > 0 else Decimal('0.00')

    total_amount = _money(delivery_fee + service_charge + insurance_fee)

    # ETA: travel time at average speed + fixed handling buffer.
    travel_minutes = (distance_km / avg_speed_kmh * Decimal('60')) if avg_speed_kmh > 0 else Decimal('0')
    estimated_minutes = int((travel_minutes + handling_minutes).to_integral_value(rounding=ROUND_HALF_UP))
    estimated_delivery_time = timezone.now() + timedelta(minutes=estimated_minutes)

    return {
        'distance_km': _money(distance_km),
        'delivery_fee': delivery_fee,
        'service_charge': service_charge,
        'insurance_fee': insurance_fee,
        'total_amount': total_amount,
        'estimated_minutes': estimated_minutes,
        'estimated_delivery_time': estimated_delivery_time,
    }
