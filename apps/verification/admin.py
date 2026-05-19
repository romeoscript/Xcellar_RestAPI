from django.contrib import admin
from .models import EmailVerification


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ['email', 'is_verified', 'attempts', 'max_attempts', 'is_expired', 'created_at', 'expires_at']
    list_filter = ['is_verified', 'created_at']
    search_fields = ['email']
    readonly_fields = ['created_at', 'updated_at', 'verified_at', 'code_hash']
    ordering = ['-created_at']

    fieldsets = (
        ('Verification Info', {
            'fields': ('email', 'code_hash')
        }),
        ('Status', {
            'fields': ('is_verified', 'verified_at', 'attempts', 'max_attempts')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'expires_at')
        }),
    )

    def is_expired(self, obj):
        """Check if verification code has expired"""
        if obj.expires_at:
            from django.utils import timezone
            return timezone.now() > obj.expires_at
        return False
    is_expired.boolean = True
    is_expired.short_description = 'Expired'
