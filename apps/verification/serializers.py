from rest_framework import serializers


class SendOTPSerializer(serializers.Serializer):
    """Serializer for sending an OTP to an email address"""
    email = serializers.EmailField(
        required=True,
        help_text='Email address to send the verification code to'
    )

    def validate_email(self, value):
        """Normalize email format"""
        return value.strip().lower()


class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying an OTP code"""
    email = serializers.EmailField(
        required=True,
        help_text='Email address the verification code was sent to'
    )
    code = serializers.CharField(
        required=True,
        min_length=4,
        max_length=10,
        help_text='OTP code received via email'
    )

    def validate_email(self, value):
        """Normalize email format"""
        return value.strip().lower()
