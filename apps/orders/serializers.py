from rest_framework import serializers
from apps.orders.models import Order, TrackingHistory, Rating


class OrderCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new order.

    Financial fields are READ ONLY here: fees are never accepted from the
    client. They are computed server-side (see apps.orders.pricing) and
    injected via serializer.save() in the view. Dropoff coordinates are
    required so the distance-based price can be calculated.
    """

    class Meta:
        model = Order
        fields = [
            'pickup_address', 'pickup_latitude', 'pickup_longitude',
            'dropoff_address', 'dropoff_latitude', 'dropoff_longitude',
            'recipient_name', 'recipient_email', 'recipient_phone',
            'recipient_alternate_phone', 'delivery_instructions',
            'require_recipient_signature',
            'parcel_type', 'parcel_description', 'parcel_condition',
            'parcel_quantity', 'parcel_weight_kg', 'parcel_financial_worth',
            'parcel_images',
            'delivery_fee', 'service_charge', 'insurance_fee', 'total_amount',
        ]
        # Fees are authoritative server-side values, not client input.
        read_only_fields = [
            'delivery_fee', 'service_charge', 'insurance_fee', 'total_amount',
        ]
        # Coordinates are mandatory for distance-based pricing.
        extra_kwargs = {
            'pickup_latitude': {'required': True, 'allow_null': False},
            'pickup_longitude': {'required': True, 'allow_null': False},
            'dropoff_latitude': {'required': True, 'allow_null': False},
            'dropoff_longitude': {'required': True, 'allow_null': False},
        }

    def validate_parcel_images(self, value):
        if len(value) > 5:
            raise serializers.ValidationError("Maximum 5 images allowed")
        return value


class RatingSerializer(serializers.ModelSerializer):
    """Read/representation serializer for a rating."""
    rater_email = serializers.EmailField(source='rater.email', read_only=True)
    courier_email = serializers.EmailField(source='courier.email', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = Rating
        fields = [
            'id', 'order', 'order_number', 'rater_email', 'courier_email',
            'score', 'comment', 'created_at',
        ]
        read_only_fields = fields


class RatingCreateSerializer(serializers.Serializer):
    """Validates the body for submitting a rating."""
    score = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default='')


class CourierLocationSerializer(serializers.Serializer):
    """Validates a courier's live location ping."""
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    note = serializers.CharField(
        required=False, allow_blank=True, default='Courier location update'
    )


class OrderQuoteSerializer(serializers.Serializer):
    """Validates input for a delivery price preview (no order is created)."""
    pickup_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    pickup_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    dropoff_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    dropoff_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    parcel_weight_kg = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True)
    parcel_financial_worth = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True)


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer for listing orders"""
    sender_email = serializers.EmailField(source='sender.email', read_only=True)
    assigned_courier_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'tracking_number',
            'sender_email', 'assigned_courier_name',
            'pickup_address', 'dropoff_address',
            'recipient_name', 'recipient_phone',
            'parcel_type', 'parcel_description',
            'status', 'total_amount', 'payment_status',
            'created_at', 'estimated_delivery_time',
        ]
    
    def get_assigned_courier_name(self, obj):
        if obj.assigned_courier:
            return obj.assigned_courier.email
        return None


class OrderDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for order view"""
    sender_email = serializers.EmailField(source='sender.email', read_only=True)
    assigned_courier_email = serializers.EmailField(source='assigned_courier.email', read_only=True)
    tracking_history = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = '__all__'
    
    def get_tracking_history(self, obj):
        history = obj.tracking_history.all()[:10]  # Last 10 updates
        return TrackingHistorySerializer(history, many=True).data


class TrackingHistorySerializer(serializers.ModelSerializer):
    """Serializer for tracking history"""
    
    class Meta:
        model = TrackingHistory
        fields = ['id', 'status', 'location', 'latitude', 'longitude', 'notes', 'created_at']


class PublicOrderTrackingSerializer(serializers.ModelSerializer):
    """Public serializer for order tracking - exposes only safe data"""
    tracking_history = TrackingHistorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'order_number', 'tracking_number', 'status',
            'current_location', 'estimated_delivery_time',
            'tracking_history'
        ]

