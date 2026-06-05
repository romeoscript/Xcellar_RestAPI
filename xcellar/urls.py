from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)
from drf_spectacular.utils import extend_schema
from django.views.generic.base import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/couriers/', include('apps.couriers.urls')),
    path('api/v1/verification/', include('apps.verification.urls')),
    path('api/v1/faq/', include('apps.faq.urls')),
    path('api/v1/help/', include('apps.help.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/core/', include('apps.core.urls')),
    path('api/v1/orders/', include('apps.orders.urls')),
    path('api/v1/marketplace/', include('apps.marketplace.urls')),
    path('api/v1/automation/', include('apps.automation.urls')),
    
    # Password reset web pages
    path('reset-password/', include('apps.accounts.password_reset.urls')),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Root redirect
    path('', RedirectView.as_view(url='/api/docs/', permanent=False)),
]


@extend_schema(exclude=True)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'service': 'xcellar-api'
    })


urlpatterns += [
    path('health/', health_check, name='health_check'),
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    try:
        import debug_toolbar
        urlpatterns += [
            path('__debug__/', include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass
else:
    # Serve media files in production
    # Note: For high-traffic production, consider using cloud storage (S3/Cloudinary)
    from django.views.static import serve
    from django.urls import re_path
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
