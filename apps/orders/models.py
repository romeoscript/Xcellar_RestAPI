from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from apps.core.models import AbstractBaseModel


class Order(AbstractBaseModel):
    """
    Parcel order model for tracking deliveries from creation to completion.
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('AVAILABLE', 'Available for Pickup'),  # After user confirms, available to couriers
        ('ASSIGNED', 'Assigned to Courier'),
        ('ACCEPTED', 'Accepted by Courier'),
        ('PICKED_UP', 'Picked Up'),
        ('IN_TRANSIT', 'In Transit'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PARCEL_TYPE_CHOICES = [
        ('FOOD', 'Food'),
        ('ELECTRONICS', 'Electronics'),
        ('DOCUMENTS', 'Documents'),
        ('CLOTHING', 'Clothing'),
        ('PERSONAL_ITEMS', 'Personal Items'),
        ('MEDICINE', 'Medicine'),
        ('OTHER', 'Other'),
    ]
    
    # Order identification
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    tracking_number = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    
    # Relationships
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_orders'
    )
    assigned_courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_orders',
        limit_choices_to={'user_type': 'COURIER'}
    )
    
    # Addresses
    pickup_address = models.TextField()
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_address = models.TextField()
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    # Recipient info (stored as JSON for flexibility)
    recipient_name = models.CharField(max_length=200)
    recipient_email = models.EmailField(null=True, blank=True)
    recipient_phone = models.CharField(max_length=20)
    recipient_alternate_phone = models.CharField(max_length=20, blank=True, null=True)
    delivery_instructions = models.TextField(blank=True)
    require_recipient_signature = models.BooleanField(default=False)
    
    # Parcel details (stored as JSON for flexibility)
    parcel_type = models.CharField(max_length=50, choices=PARCEL_TYPE_CHOICES)
    parcel_description = models.TextField()
    parcel_condition = models.CharField(max_length=50)  # e.g., "Fragile", "Normal", "Liquid"
    parcel_quantity = models.PositiveIntegerField(default=1)
    parcel_weight_kg = models.DecimalField(max_digits=8, decimal_places=2)
    parcel_financial_worth = models.DecimalField(max_digits=12, decimal_places=2)
    parcel_images = models.JSONField(default=list, blank=True)  # Store up to 5 image URLs
    
    # Financial details
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2)
    insurance_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, default='PENDING')  # PENDING, PAID, FAILED
    courier_payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    current_location = models.CharField(max_length=500, blank=True)
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)
    
    # Courier assignment
    offered_to_couriers = models.JSONField(default=list, blank=True)  # List of courier IDs offered
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['tracking_number']),
            models.Index(fields=['sender']),
            models.Index(fields=['assigned_courier']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
    
    def __str__(self):
        return f"Order {self.order_number} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            import uuid
            self.order_number = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        if not self.tracking_number:
            import uuid
            self.tracking_number = f"TRK-{uuid.uuid4().hex[:16].upper()}"
        # Auto-calculate total_amount if not set
        if not self.total_amount:
            self.total_amount = self.delivery_fee + self.service_charge + self.insurance_fee
        super().save(*args, **kwargs)


class TrackingHistory(AbstractBaseModel):
    """
    Track order status changes and location updates.
    """
    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='tracking_history'
    )
    status = models.CharField(max_length=50)
    location = models.CharField(max_length=500, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'tracking_history'
        ordering = ['-created_at']
        verbose_name = 'Tracking History'
        verbose_name_plural = 'Tracking History'
    
    def __str__(self):
        return f"{self.order.order_number} - {self.status} - {self.created_at}"


class Rating(AbstractBaseModel):
    """
    A sender's rating of the courier for a completed (delivered) order.
    One rating per order.
    """
    order = models.OneToOneField(
        'Order',
        on_delete=models.CASCADE,
        related_name='rating'
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_ratings'
    )
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_ratings',
        limit_choices_to={'user_type': 'COURIER'}
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Rating from 1 to 5'
    )
    comment = models.TextField(blank=True)

    class Meta:
        db_table = 'order_ratings'
        ordering = ['-created_at']
        verbose_name = 'Rating'
        verbose_name_plural = 'Ratings'

    def __str__(self):
        return f"{self.order.order_number} - {self.score}/5"

