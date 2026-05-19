import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class EmailVerificationService:
    """
    Service for sending OTP verification codes via email.
    """

    def send_otp(self, email, code):
        """
        Send an OTP code to an email address.

        Args:
            email: Recipient email address
            code: The plain OTP code to send

        Returns:
            tuple: (success: bool, message: str)
        """
        app_name = getattr(settings, 'APP_NAME', 'Xcellar')
        expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 5)

        context = {
            'code': code,
            'app_name': app_name,
            'expiry_minutes': expiry_minutes,
            'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@xcellar.com'),
        }

        # Render email templates
        try:
            html_message = render_to_string('verification/otp_email.html', context)
            plain_message = render_to_string('verification/otp_email.txt', context)
        except Exception as e:
            logger.error(f"Failed to render OTP email template: {e}")
            return False, "Failed to render verification email"

        # Send email
        try:
            send_mail(
                subject=f'Your {app_name} verification code',
                message=plain_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@xcellar.com'),
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False,
            )
            logger.info(f"OTP email sent to {email}")
            return True, "OTP sent successfully"
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {e}")
            return False, "Failed to send verification email"


# Singleton instance
email_verification_service = EmailVerificationService()
