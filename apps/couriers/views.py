from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.core.response import success_response, error_response, validation_error_response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, OpenApiExample
import logging

from apps.core.permissions import IsCourier
from .models import Vehicle, DriverLicense
from .serializers import VehicleSerializer, DriverLicenseSerializer

logger = logging.getLogger(__name__)


class VehicleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing courier vehicles.
    Only couriers can access their own vehicles.
    Supports file uploads for documents (registration, insurance, road worthiness).
    """
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated, IsCourier]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # Support file uploads
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['license_plate_number', 'manufacturer', 'model']
    ordering_fields = ['created_at', 'year_of_manufacturing', 'manufacturer']
    ordering = ['-created_at']
    
    def get_serializer_context(self):
        """Add request to serializer context for absolute URLs"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def get_queryset(self):
        """Return only vehicles belonging to the authenticated courier"""
        queryset = Vehicle.objects.filter(
            courier=self.request.user,
            courier__user_type='COURIER'
        )
        
        # Manual filtering via query parameters
        vehicle_type = self.request.query_params.get('vehicle_type', None)
        if vehicle_type:
            queryset = queryset.filter(vehicle_type=vehicle_type)
        
        ownership_condition = self.request.query_params.get('ownership_condition', None)
        if ownership_condition:
            queryset = queryset.filter(ownership_condition=ownership_condition)
        
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_active=is_active_bool)
        
        return queryset
    
    def perform_create(self, serializer):
        """Automatically assign vehicle to authenticated courier"""
        vehicle = serializer.save(courier=self.request.user)
        logger.info(f"Vehicle created: {vehicle.license_plate_number} for courier {self.request.user.email}")
    
    def perform_update(self, serializer):
        """Log vehicle updates"""
        vehicle = serializer.save()
        logger.info(f"Vehicle updated: {vehicle.license_plate_number} by courier {self.request.user.email}")
    
    def perform_destroy(self, instance):
        """Soft delete vehicle by setting is_active=False"""
        instance.is_active = False
        instance.save()
        logger.info(f"Vehicle deactivated: {instance.license_plate_number} by courier {self.request.user.email}")
    
    @extend_schema(
        tags=['Couriers'],
        summary='List Vehicles',
        description='List all vehicles belonging to the authenticated courier. Supports filtering and search.',
        responses={
            200: VehicleSerializer(many=True),
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Only couriers allowed'},
        },
    )
    def list(self, request, *args, **kwargs):
        """List all vehicles for authenticated courier"""
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Create Vehicle',
        description='Create a new vehicle for the authenticated courier.',
        request=VehicleSerializer,
        responses={
            201: VehicleSerializer,
            400: {'description': 'Validation error'},
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Only couriers allowed'},
        },
        examples=[
            OpenApiExample(
                'Create Vehicle Request',
                value={
                    'vehicle_type': 'MOTORCYCLE',
                    'ownership_condition': 'OWNED',
                    'manufacturer': 'Honda',
                    'model': 'CBR 600',
                    'year_of_manufacturing': 2020,
                    'license_plate_number': 'ABC-1234',
                },
                request_only=True,
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        """Create a new vehicle"""
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Get Vehicle',
        description='Retrieve a specific vehicle by ID. Only accessible by the vehicle owner.',
        responses={
            200: VehicleSerializer,
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Vehicle does not belong to you'},
            404: {'description': 'Vehicle not found'},
        },
    )
    def retrieve(self, request, *args, **kwargs):
        """Retrieve a specific vehicle"""
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Partial Update Vehicle',
        description='Partially update a vehicle. Only accessible by the vehicle owner. Supports document uploads (registration, insurance, road worthiness).',
        request=VehicleSerializer,
        responses={
            200: VehicleSerializer,
            400: {'description': 'Validation error'},
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Vehicle does not belong to you'},
            404: {'description': 'Vehicle not found'},
        },
    )
    def partial_update(self, request, *args, **kwargs):
        """Partially update a vehicle"""
        return super().partial_update(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Update Vehicle',
        description='Update a vehicle. Only accessible by the vehicle owner. Supports document uploads (registration, insurance, road worthiness).',
        request=VehicleSerializer,
        responses={
            200: VehicleSerializer,
            400: {'description': 'Validation error'},
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Vehicle does not belong to you'},
            404: {'description': 'Vehicle not found'},
        },
    )
    def update(self, request, *args, **kwargs):
        """Update a vehicle"""
        return super().update(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Delete Vehicle',
        description='Delete (deactivate) a vehicle. Only accessible by the vehicle owner.',
        responses={
            204: {'description': 'Vehicle deleted successfully'},
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Vehicle does not belong to you'},
            404: {'description': 'Vehicle not found'},
        },
    )
    def destroy(self, request, *args, **kwargs):
        """Delete (soft delete) a vehicle"""
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Activate Vehicle',
        description='Activate a vehicle. Only accessible by the vehicle owner.',
        responses={
            200: VehicleSerializer,
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Vehicle does not belong to you'},
            404: {'description': 'Vehicle not found'},
        },
    )
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a vehicle"""
        vehicle = self.get_object()
        vehicle.is_active = True
        vehicle.save()
        serializer = self.get_serializer(vehicle)
        logger.info(f"Vehicle activated: {vehicle.license_plate_number}")
        return success_response(data=serializer.data)
    
    @extend_schema(
        tags=['Couriers'],
        summary='Deactivate Vehicle',
        description='Deactivate a vehicle. Only accessible by the vehicle owner.',
        responses={
            200: VehicleSerializer,
            401: {'description': 'Authentication required'},
            403: {'description': 'Forbidden - Vehicle does not belong to you'},
            404: {'description': 'Vehicle not found'},
        },
    )
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a vehicle"""
        vehicle = self.get_object()
        vehicle.is_active = False
        vehicle.save()
        serializer = self.get_serializer(vehicle)
        logger.info(f"Vehicle deactivated: {vehicle.license_plate_number}")
        return success_response(data=serializer.data)


@extend_schema(
    tags=['Couriers'],
    summary='Get Driver License',
    description='Retrieve driver license information for the authenticated courier. Returns empty response if license not created yet.',
    responses={
        200: {
            'description': 'Driver license data or empty response',
            'examples': {
                'application/json': {
                    'id': 1,
                    'license_number': 'DL123456',
                    'issue_date': '2020-01-15',
                    'expiry_date': '2025-01-15',
                    'issuing_authority': 'DMV',
                    'front_page_url': 'http://localhost:8000/media/licenses/documents/front/license_1.jpg',
                    'back_page_url': 'http://localhost:8000/media/licenses/documents/back/license_1.jpg',
                    'vehicle_insurance': None,
                    'vehicle_insurance_url': None,
                    'vehicle_registration': None,
                    'vehicle_registration_url': None,
                    'is_expired': False,
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Forbidden - Only couriers allowed'},
    },
    examples=[
        OpenApiExample(
            'Driver License Response',
            value={
                'id': 1,
                'license_number': 'DL123456',
                'issue_date': '2020-01-15',
                'expiry_date': '2025-01-15',
                'issuing_authority': 'DMV',
                'front_page_url': 'http://localhost:8000/media/licenses/documents/front/license_1.jpg',
                'back_page_url': 'http://localhost:8000/media/licenses/documents/back/license_1.jpg',
                'vehicle_insurance': None,
                'vehicle_insurance_url': None,
                'vehicle_registration': None,
                'vehicle_registration_url': None,
                'is_expired': False,
            },
            response_only=True,
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCourier])
@ratelimit(key='user', rate='100/h', method='GET')
def driver_license(request):
    """
    Get driver license for authenticated courier.
    GET /api/v1/couriers/license/
    """
    try:
        courier_profile = request.user.courier_profile
        license_obj = courier_profile.driver_license
        serializer = DriverLicenseSerializer(license_obj, context={'request': request})
        return success_response(data=serializer.data)
    except AttributeError:
        # License not created yet (OneToOne relationship doesn't exist)
        # Django raises RelatedObjectDoesNotExist which is a subclass of AttributeError
        return success_response(
            data={'license': None},
            message='Driver license not registered yet. Use PUT/PATCH to create.'
        )
    except Exception as e:
        # Fallback exception handling
        logger.error(f"Error retrieving driver license for courier {request.user.email}: {e}")
        return success_response(
            data={'license': None},
            message='Driver license not registered yet. Use PUT/PATCH to create.'
        )


@extend_schema(
    tags=['Couriers'],
    summary='Create/Update Driver License',
    description='Create or update driver license information for the authenticated courier. Supports file uploads. Auto-creates license if it doesn\'t exist.',
    request=DriverLicenseSerializer,
    responses={
        200: {
            'description': 'Driver license created/updated successfully',
            'examples': {
                'application/json': {
                    'status': 200,
                    'message': 'Driver license updated successfully',
                    'license': {
                        'id': 1,
                        'license_number': 'DL123456',
                        'issue_date': '2020-01-15',
                        'expiry_date': '2025-01-15',
                        'issuing_authority': 'DMV',
                        'front_page_url': 'http://localhost:8000/media/licenses/documents/front/license_1.jpg',
                        'back_page_url': 'http://localhost:8000/media/licenses/documents/back/license_1.jpg',
                        'vehicle_insurance': None,
                        'vehicle_insurance_url': None,
                        'vehicle_registration': None,
                        'vehicle_registration_url': None,
                        'is_expired': False,
                    }
                }
            }
        },
        400: {'description': 'Validation error'},
        401: {'description': 'Authentication required'},
        403: {'description': 'Forbidden - Only couriers allowed'},
    },
    examples=[
        OpenApiExample(
            'Update Driver License Request',
            value={
                'license_number': 'DL123456',
                'issue_date': '2020-01-15',
                'expiry_date': '2025-01-15',
                'issuing_authority': 'DMV',
                'front_page': '<file>',
                'back_page': '<file>',
                'vehicle_insurance': '<file>',
                'vehicle_registration': '<file>',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Update Driver License Response',
            value={
                'status': 200,
                'message': 'Driver license updated successfully',
                'license': {
                    'id': 1,
                    'license_number': 'DL123456',
                    'issue_date': '2020-01-15',
                    'expiry_date': '2025-01-15',
                    'issuing_authority': 'DMV',
                    'front_page_url': 'http://localhost:8000/media/licenses/documents/front/license_1.jpg',
                    'back_page_url': 'http://localhost:8000/media/licenses/documents/back/license_1.jpg',
                    'vehicle_insurance': None,
                    'vehicle_insurance_url': None,
                    'vehicle_registration': None,
                    'vehicle_registration_url': None,
                    'is_expired': False,
                }
            },
            response_only=True,
        ),
    ],
)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated, IsCourier])
@ratelimit(key='user', rate='10/h', method=['PUT', 'PATCH'])
def update_driver_license(request):
    """
    Create or update driver license for authenticated courier.
    PUT/PATCH /api/v1/couriers/license/update/
    """
    from django.db import transaction
    
    courier_profile = request.user.courier_profile
    is_create = False
    license_obj = None
    
    try:
        license_obj = courier_profile.driver_license
        serializer = DriverLicenseSerializer(
            license_obj,
            data=request.data,
            partial=request.method == 'PATCH',
            context={'request': request}
        )
    except AttributeError:
        # License doesn't exist, create new one (OneToOne relationship doesn't exist)
        # Django raises RelatedObjectDoesNotExist which is a subclass of AttributeError
        is_create = True
        serializer = DriverLicenseSerializer(
            data=request.data,
            context={'request': request}
        )
    
    if not serializer.is_valid():
        return validation_error_response(serializer.errors, message='Validation error')
    
    try:
        with transaction.atomic():
            # Handle file deletions if replacing (save old file references before saving)
            old_front_page = None
            old_back_page = None
            old_vehicle_insurance = None
            old_vehicle_registration = None
            
            if not is_create and license_obj:
                old_front_page = license_obj.front_page
                old_back_page = license_obj.back_page
                old_vehicle_insurance = license_obj.vehicle_insurance
                old_vehicle_registration = license_obj.vehicle_registration
            
            # Save license, automatically assign to courier_profile
            license_obj = serializer.save(courier_profile=courier_profile)
            
            # Delete old files if new ones were uploaded (after saving new files)
            if 'front_page' in serializer.validated_data and old_front_page:
                old_front_page.delete(save=False)
            if 'back_page' in serializer.validated_data and old_back_page:
                old_back_page.delete(save=False)
            if 'vehicle_insurance' in serializer.validated_data and old_vehicle_insurance:
                old_vehicle_insurance.delete(save=False)
            if 'vehicle_registration' in serializer.validated_data and old_vehicle_registration:
                old_vehicle_registration.delete(save=False)
            
        logger.info(f"Driver license {'created' if is_create else 'updated'} for courier {request.user.email}")
        
        response_serializer = DriverLicenseSerializer(license_obj, context={'request': request})
        return success_response(
            data={'license': response_serializer.data},
            message=f'Driver license {"created" if is_create else "updated"} successfully'
        )
    except Exception as e:
        logger.error(f"Failed to update driver license for courier {request.user.email}: {e}")
        return error_response('Unable to update driver license information at this time. Please check your details and try again.', status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['Couriers'],
    summary='Courier Dashboard',
    description='Get courier dashboard information. Available only for couriers (COURIER type).',
    responses={
        200: {
            'description': 'Courier dashboard data',
            'examples': {
                'application/json': {
                    'message': 'Courier dashboard',
                    'courier': 'courier@example.com',
                }
            }
        },
        401: {'description': 'Authentication required'},
        403: {'description': 'Forbidden - Only COURIER type allowed'},
        429: {'description': 'Rate limit exceeded (100 requests per hour)'},
    },
    examples=[
        OpenApiExample(
            'Courier Dashboard Response',
            value={
                'message': 'Courier dashboard',
                'courier': 'courier@example.com',
            },
            response_only=True,
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsCourier])
@ratelimit(key='user', rate='100/h', method='GET')
def courier_dashboard(request):
    """
    Courier dashboard endpoint.
    GET /api/v1/couriers/dashboard/
    """
    from django.db.models import Avg
    from apps.orders.models import Order
    from apps.orders.serializers import OrderListSerializer

    user = request.user
    profile = getattr(user, 'courier_profile', None)
    assigned = Order.objects.filter(assigned_courier=user)
    active_statuses = ['ACCEPTED', 'PICKED_UP', 'IN_TRANSIT']

    rating_stats = user.received_ratings.aggregate(avg=Avg('score'))
    average_rating = round(rating_stats['avg'], 2) if rating_stats['avg'] is not None else None
    ratings_count = user.received_ratings.count()

    # Count open offers waiting for this courier (JSON membership -> Python side).
    open_offers = Order.objects.filter(status='AVAILABLE', assigned_courier__isnull=True)[:100]
    available_requests = sum(
        1 for o in open_offers if user.id in (o.offered_to_couriers or [])
    )

    data = {
        'email': user.email,
        'balance': str(profile.balance) if profile else '0.00',
        'is_available': profile.is_available if profile else False,
        'active_deliveries': assigned.filter(status__in=active_statuses).count(),
        'completed_deliveries': assigned.filter(status='DELIVERED').count(),
        'total_deliveries': assigned.count(),
        'available_requests': available_requests,
        'average_rating': average_rating,
        'ratings_count': ratings_count,
        'recent_deliveries': OrderListSerializer(assigned[:5], many=True).data,
    }
    return success_response(data=data, message='Courier dashboard')

