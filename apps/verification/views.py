from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from apps.core.response import success_response, error_response, validation_error_response
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, OpenApiExample
from django.conf import settings

from .models import EmailVerification
from .serializers import SendOTPSerializer, VerifyOTPSerializer
from .utils import generate_otp_code, hash_otp_code, verify_otp_code, get_otp_expiry_time
from .services import email_verification_service


@extend_schema(
    tags=['Verification'],
    summary='Send OTP',
    description='Send an OTP code to an email address. Rate limited to prevent abuse.',
    request=SendOTPSerializer,
    responses={
        200: {
            'description': 'OTP sent successfully',
            'examples': {
                'application/json': {
                    'message': 'OTP sent successfully',
                    'expires_in': 300,
                }
            }
        },
        400: {'description': 'Validation error - check request body'},
        429: {'description': 'Rate limit exceeded'},
    },
    examples=[
        OpenApiExample(
            'Send OTP Request',
            value={
                'email': 'user@example.com',
            },
            request_only=True,
        ),
    ],
)
@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/h', method='POST')
def send_otp(request):
    """
    Send an OTP code to an email address.
    POST /api/v1/verification/send/
    """
    serializer = SendOTPSerializer(data=request.data)
    if not serializer.is_valid():
        return validation_error_response(serializer.errors, message='Validation error')

    email = serializer.validated_data['email']

    # Check cooldown period (prevent spam)
    cooldown_seconds = getattr(settings, 'OTP_COOLDOWN_SECONDS', 60)
    recent_verification = EmailVerification.objects.filter(
        email=email,
        created_at__gte=timezone.now() - timezone.timedelta(seconds=cooldown_seconds)
    ).first()

    if recent_verification:
        remaining = cooldown_seconds - int((timezone.now() - recent_verification.created_at).total_seconds())
        return error_response(
            f'Please wait {remaining} seconds before requesting another OTP',
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            data={'cooldown_remaining': remaining}
        )

    # Generate a new OTP code and hash it for storage
    code = generate_otp_code()
    code_hash, _ = hash_otp_code(code)
    expires_at = get_otp_expiry_time()
    max_attempts = getattr(settings, 'OTP_MAX_ATTEMPTS', 3)

    # Send OTP via email
    success, message = email_verification_service.send_otp(email, code)

    if not success:
        return error_response(message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Invalidate any existing unverified OTPs for this email
    EmailVerification.objects.filter(
        email=email,
        is_verified=False
    ).update(is_active=False)

    # Create verification record
    EmailVerification.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at,
        max_attempts=max_attempts,
    )

    expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 5)
    return success_response(
        data={'expires_in': expiry_minutes * 60},
        message='OTP sent successfully'
    )


@extend_schema(
    tags=['Verification'],
    summary='Verify OTP',
    description='Verify an OTP code sent to an email address. Code expires after a few minutes.',
    request=VerifyOTPSerializer,
    responses={
        200: {
            'description': 'OTP verified successfully',
            'examples': {
                'application/json': {
                    'verified': True,
                    'message': 'Email verified successfully',
                }
            }
        },
        400: {'description': 'Invalid OTP code or validation error'},
        429: {'description': 'Too many verification attempts'},
    },
    examples=[
        OpenApiExample(
            'Verify OTP Request',
            value={
                'email': 'user@example.com',
                'code': '123456',
            },
            request_only=True,
        ),
    ],
)
@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='20/h', method='POST')
def verify_otp(request):
    """
    Verify an OTP code sent to an email address.
    POST /api/v1/verification/verify/
    """
    serializer = VerifyOTPSerializer(data=request.data)
    if not serializer.is_valid():
        return validation_error_response(serializer.errors, message='Validation error')

    email = serializer.validated_data['email']
    code = serializer.validated_data['code']

    # Find the latest unverified, active OTP for this email
    verification = EmailVerification.objects.filter(
        email=email,
        is_verified=False,
        is_active=True
    ).order_by('-created_at').first()

    if not verification:
        return error_response('No active verification code found. Please request a new verification code.', status_code=status.HTTP_400_BAD_REQUEST)

    # Check if expired
    if verification.is_expired():
        return error_response('Verification code has expired. Please request a new verification code.', status_code=status.HTTP_400_BAD_REQUEST)

    # Check attempts
    if not verification.can_attempt():
        if verification.attempts >= verification.max_attempts:
            return error_response('Too many verification attempts. Please request a new verification code and try again.', status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    # Verify the code against the stored hash
    if verify_otp_code(code, verification.code_hash):
        verification.mark_verified()
        return success_response(
            data={'verified': True},
            message='Email verified successfully'
        )
    else:
        verification.increment_attempts()
        remaining_attempts = verification.max_attempts - verification.attempts
        return error_response(
            'Invalid or expired OTP code',
            status_code=status.HTTP_400_BAD_REQUEST,
            data={'remaining_attempts': max(remaining_attempts, 0)}
        )
