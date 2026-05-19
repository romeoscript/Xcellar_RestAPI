from django.db import models
from django.utils import timezone
from apps.core.models import AbstractBaseModel


class EmailVerification(AbstractBaseModel):
    """
    Model to store email verification OTP codes.
    """
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=255)  # Hashed OTP code (format: "salt:hash")
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'email_verifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'created_at']),
            models.Index(fields=['email', 'is_verified']),
        ]
        verbose_name = 'Email Verification'
        verbose_name_plural = 'Email Verifications'

    def __str__(self):
        return f"{self.email} - {'verified' if self.is_verified else 'pending'}"

    def is_expired(self):
        """Check if verification code has expired"""
        return timezone.now() > self.expires_at

    def can_attempt(self):
        """Check if more verification attempts are allowed"""
        return self.attempts < self.max_attempts and not self.is_expired() and not self.is_verified

    def mark_verified(self):
        """Mark verification as successful"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save(update_fields=['is_verified', 'verified_at'])

    def increment_attempts(self):
        """Increment verification attempts"""
        self.attempts += 1
        self.save(update_fields=['attempts'])
