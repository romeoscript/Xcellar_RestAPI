from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from apps.core.response import success_response
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, OpenApiExample

from apps.core.permissions import IsUser
from apps.orders.models import Order
from apps.orders.serializers import OrderListSerializer

# Statuses where an order is in flight (placed, being matched, or en route).
ACTIVE_ORDER_STATUSES = ['AVAILABLE', 'ASSIGNED', 'ACCEPTED', 'PICKED_UP', 'IN_TRANSIT']


@extend_schema(
    tags=['Users'],
    summary='User Dashboard',
    description='Get user dashboard information. Available only for regular customers (USER type).',
    responses={
        200: {
            'description': 'User dashboard data',
            'examples': {
                'application/json': {
                    'message': 'User dashboard',
                    'user': 'user@example.com',
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Forbidden - Only USER type allowed'},
        429: {'description': 'Rate limit exceeded (100 requests per hour)'},
    },
    examples=[
        OpenApiExample(
            'User Dashboard Response',
            value={
                'message': 'User dashboard',
                'user': 'user@example.com',
            },
            response_only=True,
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsUser])
@ratelimit(key='user', rate='100/h', method='GET')
def user_dashboard(request):
    """
    User dashboard endpoint.
    GET /api/v1/users/dashboard/
    """
    user = request.user
    profile = getattr(user, 'user_profile', None)
    orders = Order.objects.filter(sender=user)

    data = {
        'email': user.email,
        'balance': str(profile.balance) if profile else '0.00',
        'total_orders': orders.count(),
        'active_orders': orders.filter(status__in=ACTIVE_ORDER_STATUSES).count(),
        'pending_orders': orders.filter(status='PENDING').count(),
        'delivered_orders': orders.filter(status='DELIVERED').count(),
        'cancelled_orders': orders.filter(status='CANCELLED').count(),
        'recent_orders': OrderListSerializer(orders[:5], many=True).data,
    }
    return success_response(data=data, message='User dashboard')

