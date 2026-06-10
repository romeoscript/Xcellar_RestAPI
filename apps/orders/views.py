from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.core.response import success_response, error_response, created_response, validation_error_response, not_found_response
from drf_spectacular.utils import extend_schema, OpenApiExample
from django.utils import timezone
from django.db import transaction as db_transaction, IntegrityError
from django.db.models import Q
from django_ratelimit.decorators import ratelimit
import logging

from apps.orders.models import Order, TrackingHistory
from apps.orders.serializers import (
    OrderCreateSerializer,
    OrderQuoteSerializer,
    OrderListSerializer,
    OrderDetailSerializer,
    TrackingHistorySerializer,
    PublicOrderTrackingSerializer,
    RatingSerializer,
    RatingCreateSerializer,
    CourierLocationSerializer,
)
from apps.orders.models import Rating
from apps.orders.pricing import quote_delivery, haversine_km
from apps.core.permissions import IsUser, IsCourier
from apps.accounts.models import User

logger = logging.getLogger(__name__)

# Human-readable labels + icon keywords for tracking-timeline entries.
STATUS_DISPLAY = {
    'PENDING': 'Order Placed',
    'AVAILABLE': 'Finding Courier',
    'ASSIGNED': 'Courier Assigned',
    'ACCEPTED': 'Courier Accepted',
    'PICKED_UP': 'Picked Up',
    'IN_TRANSIT': 'In Transit',
    'DELIVERED': 'Delivered',
    'CANCELLED': 'Cancelled',
}
STATUS_ICON = {
    'PENDING': 'receipt',
    'AVAILABLE': 'search',
    'ASSIGNED': 'person',
    'ACCEPTED': 'check',
    'PICKED_UP': 'inventory',
    'IN_TRANSIT': 'local_shipping',
    'DELIVERED': 'done_all',
    'CANCELLED': 'cancel',
}


@extend_schema(
    tags=['Orders'],
    summary='Create Order',
    description='Create a new parcel order',
    request=OrderCreateSerializer,
    responses={201: OrderDetailSerializer}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsUser])
def create_order(request):
    """Create a new parcel order with server-computed fees."""
    serializer = OrderCreateSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data

        # Authoritative pricing — never trust client-supplied fees.
        quote = quote_delivery(
            pickup_latitude=data['pickup_latitude'],
            pickup_longitude=data['pickup_longitude'],
            dropoff_latitude=data['dropoff_latitude'],
            dropoff_longitude=data['dropoff_longitude'],
            parcel_weight_kg=data.get('parcel_weight_kg'),
            parcel_financial_worth=data.get('parcel_financial_worth'),
        )

        order = serializer.save(
            sender=request.user,
            status='PENDING',
            delivery_fee=quote['delivery_fee'],
            service_charge=quote['service_charge'],
            insurance_fee=quote['insurance_fee'],
            total_amount=quote['total_amount'],
            estimated_delivery_time=quote['estimated_delivery_time'],
        )

        # Create initial tracking entry
        TrackingHistory.objects.create(
            order=order,
            status='PENDING',
            notes='Order placed successfully'
        )

        return created_response(data={'order': OrderDetailSerializer(order).data}, message='Order created successfully')
    return validation_error_response(serializer.errors, message='Validation error')


@extend_schema(
    tags=['Orders'],
    summary='Quote Delivery',
    description='Preview the delivery fee for a pickup/dropoff pair before creating an order. No order is created.',
    request=OrderQuoteSerializer,
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsUser])
def quote_order(request):
    """Return an authoritative delivery price preview (no side effects)."""
    serializer = OrderQuoteSerializer(data=request.data)
    if not serializer.is_valid():
        return validation_error_response(serializer.errors, message='Validation error')

    data = serializer.validated_data
    quote = quote_delivery(
        pickup_latitude=data['pickup_latitude'],
        pickup_longitude=data['pickup_longitude'],
        dropoff_latitude=data['dropoff_latitude'],
        dropoff_longitude=data['dropoff_longitude'],
        parcel_weight_kg=data.get('parcel_weight_kg'),
        parcel_financial_worth=data.get('parcel_financial_worth'),
    )

    return success_response(
        data={
            'distance_km': str(quote['distance_km']),
            'delivery_fee': str(quote['delivery_fee']),
            'service_charge': str(quote['service_charge']),
            'insurance_fee': str(quote['insurance_fee']),
            'total_amount': str(quote['total_amount']),
            'estimated_minutes': quote['estimated_minutes'],
            'estimated_delivery_time': quote['estimated_delivery_time'].isoformat(),
        },
        message='Delivery quote calculated',
    )


@extend_schema(
    tags=['Orders'],
    summary='Rate Order',
    description='Rate the courier for a delivered order (sender only, once per order).',
    request=RatingCreateSerializer,
    responses={201: RatingSerializer},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsUser])
def rate_order(request, order_id):
    """Submit a courier rating for a delivered order."""
    try:
        order = Order.objects.get(id=order_id, sender=request.user)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')

    if order.status != 'DELIVERED':
        return error_response(
            'You can only rate an order after it has been delivered.',
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not order.assigned_courier:
        return error_response(
            'This order has no assigned courier to rate.',
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if hasattr(order, 'rating'):
        return error_response(
            'You have already rated this order.',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    serializer = RatingCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return validation_error_response(serializer.errors, message='Validation error')

    try:
        rating = Rating.objects.create(
            order=order,
            rater=request.user,
            courier=order.assigned_courier,
            score=serializer.validated_data['score'],
            comment=serializer.validated_data.get('comment', ''),
        )
    except IntegrityError:
        # Lost a race against a concurrent rating for the same order.
        return error_response(
            'You have already rated this order.',
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return created_response(
        data={'rating': RatingSerializer(rating).data},
        message='Rating submitted successfully',
    )


@extend_schema(
    tags=['Orders'],
    summary='Cancel Order',
    description='Cancel an order before pickup. If it was already paid, the amount is refunded to the wallet.',
    responses={200: OrderDetailSerializer},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsUser])
def cancel_order(request, order_id):
    """Cancel an order (sender only) and refund to wallet if it was paid."""
    import uuid
    from decimal import Decimal
    from django.db.models import F
    from apps.payments.models import Transaction, Notification

    if not Order.objects.filter(id=order_id, sender=request.user).exists():
        return not_found_response('Order not found. Please check the order ID and try again.')

    cancellable = ['PENDING', 'AVAILABLE', 'ASSIGNED']
    refunded_amount = Decimal('0.00')
    with db_transaction.atomic():
        # Lock the row so two concurrent cancels can't both refund.
        order = Order.objects.select_for_update().get(id=order_id, sender=request.user)

        # Only cancellable before a courier has picked it up.
        if order.status not in cancellable:
            return error_response(
                f'This order can no longer be cancelled (status: {order.get_status_display()}).',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Refund to the sender's wallet if the order was already paid.
        if order.payment_status == 'PAID':
            profile = getattr(request.user, 'user_profile', None)
            if profile:
                profile.__class__.objects.filter(pk=profile.pk).update(
                    balance=F('balance') + order.total_amount
                )
                profile.refresh_from_db()
                refunded_amount = order.total_amount

                txn = Transaction.objects.create(
                    user=request.user,
                    transaction_type='DEPOSIT',
                    status='SUCCESS',
                    payment_method='PAYSTACK_BALANCE',
                    amount=order.total_amount,
                    net_amount=order.total_amount,
                    reference=f'REFUND-{uuid.uuid4().hex[:20].upper()}',
                    description=f'Refund for cancelled order {order.order_number}',
                    completed_at=timezone.now(),
                    metadata={'order_id': order.id, 'order_number': order.order_number},
                )
                Notification.objects.create(
                    user=request.user,
                    notification_type='DEPOSIT_RECEIVED',
                    title='Order Refunded',
                    message=f'You were refunded ₦{order.total_amount:,.2f} for cancelled order {order.order_number}',
                    related_transaction=txn,
                    metadata={'order_number': order.order_number},
                )
                order.payment_status = 'REFUNDED'

        order.status = 'CANCELLED'
        order.cancelled_at = timezone.now()
        order.save()

        TrackingHistory.objects.create(
            order=order,
            status='CANCELLED',
            notes='Order cancelled by sender' + (
                f'; ₦{refunded_amount:,.2f} refunded to wallet'
                if refunded_amount > 0 else ''
            ),
        )

    return success_response(
        data={
            'order': OrderDetailSerializer(order).data,
            'refunded_amount': str(refunded_amount),
        },
        message='Order cancelled successfully',
    )


@extend_schema(
    tags=['Orders'],
    summary='Update Courier Location',
    description='Assigned courier posts their live GPS location for an in-progress order. Updates current location and appends to tracking history.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourier])
def update_courier_location(request, order_id):
    """Assigned courier pushes a live location ping for an active order."""
    try:
        order = Order.objects.get(id=order_id, assigned_courier=request.user)
    except Order.DoesNotExist:
        return not_found_response('Order not found or not assigned to you.')

    serializer = CourierLocationSerializer(data=request.data)
    if not serializer.is_valid():
        return validation_error_response(serializer.errors, message='Validation error')

    # Only meaningful while the parcel is actively being delivered.
    if order.status not in ['ACCEPTED', 'PICKED_UP', 'IN_TRANSIT']:
        return error_response(
            f'Location updates are only accepted for active deliveries (status: {order.get_status_display()}).',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    lat = serializer.validated_data['latitude']
    lng = serializer.validated_data['longitude']
    note = serializer.validated_data['note']

    # Reflect on the order and the courier profile (drives proximity matching).
    order.current_location = f'{lat},{lng}'
    order.save(update_fields=['current_location', 'updated_at'])

    profile = getattr(request.user, 'courier_profile', None)
    if profile:
        profile.current_location = {'latitude': float(lat), 'longitude': float(lng)}
        profile.save(update_fields=['current_location', 'updated_at'])

    TrackingHistory.objects.create(
        order=order,
        status=order.status,
        location=str(note),
        latitude=lat,
        longitude=lng,
        notes=note,
    )

    return success_response(
        data={'order': PublicOrderTrackingSerializer(order).data},
        message='Location updated',
    )


@extend_schema(
    tags=['Orders'],
    summary='Confirm Order',
    description='Confirm order and make it available to couriers',
    responses={200: OrderDetailSerializer}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsUser])
def confirm_order(request, order_id):
    """Confirm order and make it available to couriers"""
    try:
        order = Order.objects.get(id=order_id, sender=request.user)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')
    
    if order.status != 'PENDING':
        return error_response(f'This order is already {order.get_status_display().lower()}.', status_code=status.HTTP_400_BAD_REQUEST)
    
    if order.payment_status != 'PAID':
        return error_response('Order must be paid before it can be confirmed and sent to couriers.', status_code=status.HTTP_400_BAD_REQUEST)
    
    # Update order status to available
    order.status = 'AVAILABLE'
    order.save()
    
    # Create tracking entry
    TrackingHistory.objects.create(
        order=order,
        status='AVAILABLE',
        notes='Order confirmed and sent to couriers'
    )
    
    # Offer the order to the nearest available couriers.
    assign_order_to_couriers(order)
    return success_response(data=OrderDetailSerializer(order).data, message='Order confirmed successfully')


def _courier_distance_km(order, courier):
    """Distance (km) from the order's pickup point to a courier's last known
    location, or None when either coordinate is unavailable."""
    profile = getattr(courier, 'courier_profile', None)
    loc = getattr(profile, 'current_location', None) or {}
    lat = loc.get('latitude', loc.get('lat'))
    lng = loc.get('longitude', loc.get('lng'))
    if (lat is None or lng is None or
            order.pickup_latitude is None or order.pickup_longitude is None):
        return None
    try:
        return haversine_km(order.pickup_latitude, order.pickup_longitude, lat, lng)
    except (TypeError, ValueError):
        return None


def assign_order_to_couriers(order):
    """
    Offer the order to the nearest available couriers.

    Couriers are ranked by distance from the pickup location (using their last
    known location). Those who have marked themselves available are preferred;
    couriers without a known location are considered last so the system still
    works before location sharing is widespread.
    """
    available_couriers = list(
        User.objects.filter(
            user_type='COURIER',
            is_active=True,
        )
        .exclude(id__in=order.offered_to_couriers or [])
        .select_related('courier_profile')
    )

    if not available_couriers:
        # Create tracking entry noting no couriers available
        TrackingHistory.objects.create(
            order=order,
            status='AVAILABLE',
            notes='Order available but no couriers currently available'
        )
        return

    # Prefer couriers who flagged themselves available; fall back to all active.
    preferred = [
        c for c in available_couriers
        if getattr(getattr(c, 'courier_profile', None), 'is_available', False)
    ]
    pool = preferred or available_couriers

    # Rank by proximity to pickup; couriers with no location go to the back.
    def sort_key(courier):
        distance = _courier_distance_km(order, courier)
        return (0, distance) if distance is not None else (1, 0.0)

    pool.sort(key=sort_key)

    # Offer to the nearest few couriers.
    num_to_select = min(5, len(pool))
    selected_couriers = pool[:num_to_select]

    order.offered_to_couriers = [c.id for c in selected_couriers]
    order.offer_expires_at = timezone.now() + timezone.timedelta(hours=24)
    order.save()
    
    # Create single tracking entry for courier assignment
    courier_emails = [c.email for c in selected_couriers]
    TrackingHistory.objects.create(
        order=order,
        status='AVAILABLE',
        notes=f'Order sent to {len(selected_couriers)} courier(s) for pickup'
    )


@extend_schema(
    tags=['Orders'],
    summary='List Orders',
    description='List user orders with filtering',
    responses={200: OrderListSerializer}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_orders(request):
    """List orders for authenticated user"""
    user = request.user
    queryset = Order.objects.all()
    
    # Filter based on user type
    if user.user_type == 'USER':
        queryset = queryset.filter(sender=user)
    elif user.user_type == 'COURIER':
        queryset = queryset.filter(assigned_courier=user)
    
    # Filter by status if provided
    status_filter = request.query_params.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    serializer = OrderListSerializer(queryset, many=True)
    return success_response(data={'orders': serializer.data})


@extend_schema(
    tags=['Orders'],
    summary='Order Detail',
    description='Get order details with tracking history',
    responses={200: OrderDetailSerializer}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    """Get order details"""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')
    
    # Check permission
    user = request.user
    if user.user_type == 'USER' and order.sender != user:
        return error_response('You do not have permission to access this order.', status_code=status.HTTP_403_FORBIDDEN)
    elif user.user_type == 'COURIER' and order.assigned_courier != user:
        return error_response('You do not have permission to access this order.', status_code=status.HTTP_403_FORBIDDEN)
    
    serializer = OrderDetailSerializer(order)
    return success_response(data={'order': serializer.data})


@extend_schema(
    tags=['Orders'],
    summary='Track Order',
    description='Get tracking history for an order',
    responses={200: TrackingHistorySerializer}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def track_order(request, order_id):
    """Get tracking history for an order"""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')
    
    # Check permission
    user = request.user
    if user.user_type == 'USER' and order.sender != user:
        return error_response('You do not have permission to access this order.', status_code=status.HTTP_403_FORBIDDEN)
    elif user.user_type == 'COURIER' and order.assigned_courier != user:
        return error_response('You do not have permission to access this order.', status_code=status.HTTP_403_FORBIDDEN)
    
    # Oldest-first timeline for display.
    tracking = order.tracking_history.all().order_by('created_at')
    timeline = [
        {
            'date': th.created_at.isoformat(),
            'status': th.status,
            'status_display': STATUS_DISPLAY.get(th.status, th.status),
            'icon': STATUS_ICON.get(th.status, 'circle'),
            'message': th.notes or '',
            'location': th.location or None,
        }
        for th in tracking
    ]

    return success_response(
        data={
            'tracking_number': order.tracking_number,
            'pickup_address': order.pickup_address,
            'dropoff_address': order.dropoff_address,
            'recipient_name': order.recipient_name,
            'estimated_delivery': order.estimated_delivery_time.isoformat()
                if order.estimated_delivery_time else None,
            'current_status': order.status,
            'current_status_display': order.get_status_display(),
            'current_location': order.current_location or None,
            'timeline': timeline,
        },
        message='Tracking information',
    )


@extend_schema(
    tags=['Orders'],
    summary='Public Order Tracking',
    description='Track order status by tracking code (public endpoint)',
    responses={200: PublicOrderTrackingSerializer}
)
@api_view(['GET'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='100/h', method='GET')  # Allow 100 requests per hour per IP
def public_track_order(request, tracking_code):
    """Public endpoint to track order by tracking code"""
    try:
        order = Order.objects.get(tracking_number=tracking_code.upper())
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check your tracking code.')
    
    serializer = PublicOrderTrackingSerializer(order)
    return success_response(data={'order': serializer.data})


@extend_schema(
    tags=['Couriers'],
    summary='List Available Orders',
    description='List orders available for courier pickup',
    responses={200: OrderListSerializer}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCourier])
def available_orders(request):
    """List orders available for courier to accept"""
    courier_id = request.user.id
    
    # Find orders where this courier is in the offered_to_couriers list
    # We need to check each order's JSON field manually since we can't query JSON directly in all DB backends
    all_orders = Order.objects.filter(
        status='AVAILABLE',
        assigned_courier__isnull=True
    )[:100]  # Limit to 100 for performance
    
    # Filter orders where courier_id is in the offered_to_couriers list
    available_orders_list = [
        order for order in all_orders 
        if courier_id in (order.offered_to_couriers or [])
    ]
    
    serializer = OrderListSerializer(available_orders_list, many=True)
    return success_response(data={'orders': serializer.data})


@extend_schema(
    tags=['Couriers'],
    summary='Accept Order',
    description='Accept an order for delivery (atomic operation)',
    responses={200: OrderDetailSerializer}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourier])
def accept_order(request, order_id):
    """Accept an order for delivery"""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')
    
    # Atomic acceptance with select_for_update to prevent race conditions
    with db_transaction.atomic():
        # Lock the order row
        order = Order.objects.select_for_update().get(id=order_id)
        
        # Check if order is available
        if order.status != 'AVAILABLE':
            return error_response('This order is no longer available for acceptance.', status_code=status.HTTP_400_BAD_REQUEST)
        
        # Check if already assigned
        if order.assigned_courier is not None:
            return error_response('This order has already been assigned to another courier.', status_code=status.HTTP_400_BAD_REQUEST)
        
        # Assign to this courier
        order.assigned_courier = request.user
        order.status = 'ACCEPTED'
        order.save()
        
        # Create tracking entry
        TrackingHistory.objects.create(
            order=order,
            status='ACCEPTED',
            notes='Courier assigned and en route to pickup location'
        )
    
    serializer = OrderDetailSerializer(order)
    return success_response(data={'order': serializer.data})


@extend_schema(
    tags=['Couriers'],
    summary='Reject Order',
    description='Reject an offered order',
    responses={200: {'message': 'Order rejected'}}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourier])
def reject_order(request, order_id):
    """Reject an offered order"""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')
    
    # Remove courier from offered list
    offered_list = order.offered_to_couriers or []
    if request.user.id in offered_list:
        offered_list = [cid for cid in offered_list if cid != request.user.id]
        order.offered_to_couriers = offered_list
        order.save()
    
    return success_response(message='Order rejected successfully')


@extend_schema(
    tags=['Couriers'],
    summary='Update Order Status',
    description='Update order status during delivery',
    request={'application/json': {'type': 'object', 'properties': {'status': {'type': 'string'}}}},
    responses={200: OrderDetailSerializer}
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsCourier])
def update_order_status(request, order_id):
    """Update order status during delivery"""
    try:
        order = Order.objects.get(id=order_id, assigned_courier=request.user)
    except Order.DoesNotExist:
        return not_found_response('Order not found. Please check the order ID and try again.')
    
    new_status = request.data.get('status')
    if not new_status:
        return error_response('Order status is required to update the order.', status_code=status.HTTP_400_BAD_REQUEST)
    
    # Validate status transition
    valid_transitions = {
        'ACCEPTED': ['PICKED_UP'],
        'PICKED_UP': ['IN_TRANSIT'],
        'IN_TRANSIT': ['DELIVERED'],
    }
    
    if order.status not in valid_transitions:
        return error_response(f'Cannot update order status from {order.get_status_display()} to the requested status.', status_code=status.HTTP_400_BAD_REQUEST)
    
    if new_status not in valid_transitions[order.status]:
        return error_response(f'Invalid status update. Cannot change order from {order.get_status_display()} to {new_status}.', status_code=status.HTTP_400_BAD_REQUEST)
    
    # Update status
    order.status = new_status
    
    # Set timestamps
    if new_status == 'PICKED_UP':
        order.picked_up_at = timezone.now()
    elif new_status == 'DELIVERED':
        order.delivered_at = timezone.now()
    
    order.save()
    
    # Create tracking entry
    location = request.data.get('location', '')
    notes = request.data.get('notes', '')
    
    # Provide default notes if none given
    if not notes:
        default_notes = {
            'PICKED_UP': 'Package picked up from sender',
            'IN_TRANSIT': 'Package in transit to delivery location',
            'DELIVERED': 'Package delivered successfully'
        }
        notes = default_notes.get(new_status, f'Status updated to {new_status}')
    
    TrackingHistory.objects.create(
        order=order,
        status=new_status,
        location=location,
        notes=notes
    )
    
    serializer = OrderDetailSerializer(order)
    return success_response(data={'order': serializer.data})

