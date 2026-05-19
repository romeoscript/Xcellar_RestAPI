from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
# Only load if not running in Docker (Docker Compose handles env_file)
# Check if we're in Docker by looking for common Docker environment variables
is_docker = os.environ.get('DOCKER_CONTAINER') == 'true' or os.path.exists('/.dockerenv')
if not is_docker:
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        # Try default location
        load_dotenv()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-this-in-production')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_extensions',
    'drf_spectacular',
    
    # Local apps
    'apps.core',
    'apps.accounts',
    'apps.users',
    'apps.couriers',
    'apps.verification',
    'apps.faq',
    'apps.help',
    'apps.payments',
    'apps.orders',
    'apps.marketplace',
    'django_celery_beat',  # Celery Beat scheduler
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'xcellar.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'xcellar.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.CustomPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# JWT Settings
from datetime import timedelta
# Calculate 6 months in days (approximately 180 days)
# Access token: 6 months (180 days)
# Refresh token: 1 year (365 days) - allows users to refresh for a full year
# Users can still logout to invalidate tokens
JWT_ACCESS_TOKEN_DAYS = int(os.environ.get('JWT_ACCESS_TOKEN_DAYS', 180))  # 6 months default
JWT_REFRESH_TOKEN_DAYS = int(os.environ.get('JWT_REFRESH_TOKEN_DAYS', 365))  # 1 year default

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=JWT_ACCESS_TOKEN_DAYS),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=JWT_REFRESH_TOKEN_DAYS),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
}

# Custom JWT Token Serializer to include user_type
SIMPLE_JWT['TOKEN_OBTAIN_SERIALIZER'] = 'apps.accounts.serializers.CustomTokenObtainPairSerializer'

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Rate Limiting
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'

# Redis Cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f"redis://{os.environ.get('REDIS_HOST', 'redis')}:{os.environ.get('REDIS_PORT', '6379')}/1",
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Session Cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'


# Celery Configuration
CELERY_BROKER_URL = f"redis://{os.environ.get('REDIS_HOST', 'redis')}:{os.environ.get('REDIS_PORT', '6379')}/0"
CELERY_RESULT_BACKEND = f"redis://{os.environ.get('REDIS_HOST', 'redis')}:{os.environ.get('REDIS_PORT', '6379')}/0"
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Celery Task Configuration
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_EXCHANGE = 'default'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'default'

# Task routing
CELERY_TASK_ROUTES = {
    'apps.payments.tasks.process_dva_deposit': {'queue': 'high_priority'},
    'apps.payments.tasks.verify_dva_transaction': {'queue': 'medium_priority'},
    'apps.payments.tasks.sync_pending_dva_transactions': {'queue': 'low_priority'},
}

# Task retry configuration
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Celery Beat Configuration (for periodic tasks)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Paystack Settings
# Get from environment (loaded by Docker Compose via env_file or dotenv for local)
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '').strip()
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '').strip()
PAYSTACK_WEBHOOK_SECRET = os.environ.get('PAYSTACK_WEBHOOK_SECRET', '').strip()

# Email Verification (OTP) Settings
OTP_EXPIRY_MINUTES = int(os.environ.get('OTP_EXPIRY_MINUTES', 5))
OTP_MAX_ATTEMPTS = int(os.environ.get('OTP_MAX_ATTEMPTS', 3))
OTP_RATE_LIMIT_PER_HOUR = int(os.environ.get('OTP_RATE_LIMIT_PER_HOUR', 3))
OTP_COOLDOWN_SECONDS = int(os.environ.get('OTP_COOLDOWN_SECONDS', 60))

# Email Configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Xcellar <noreply@xcellar.com>')

# Password Reset Settings
PASSWORD_RESET_URL = os.environ.get('PASSWORD_RESET_URL', 'http://localhost:8000/reset-password')
PASSWORD_RESET_TOKEN_EXPIRY = int(os.environ.get('PASSWORD_RESET_TOKEN_EXPIRY', 15))  # minutes
APP_NAME = os.environ.get('APP_NAME', 'Xcellar')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@xcellar.com')
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:8000/api/v1')
DEEP_LINK_SCHEME = os.environ.get('DEEP_LINK_SCHEME', 'xcellar')

# drf-spectacular Settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'Xcellar API',
    'DESCRIPTION': '''
    Xcellar API - Mobile Application Backend
    
    A scalable Django REST Framework backend for mobile applications.
    
    ## Features
    - User authentication with JWT tokens
    - Multi-user type support (Regular Users and Couriers)
    - Role-based permissions
    - Rate limiting
    
    ## Authentication
    Use the "Authorize" button below to authenticate with a JWT token.
    Tokens are obtained through the login endpoint.
    ''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/v1',
    'TAGS': [
        {'name': 'Authentication', 'description': 'User authentication and registration endpoints'},
        {'name': 'Users', 'description': 'Regular customer endpoints'},
        {'name': 'Couriers', 'description': 'Courier/driver endpoints'},
        {'name': 'Verification', 'description': 'Email verification endpoints'},
        {'name': 'FAQ', 'description': 'Frequently asked questions endpoints'},
        {'name': 'Help', 'description': 'Help and support request endpoints'},
        {'name': 'Payments', 'description': 'Payment and transaction endpoints'},
        {'name': 'Core', 'description': 'Core service endpoints'},
        {'name': 'Orders', 'description': 'Parcel delivery and order management endpoints'},
        {'name': 'Marketplace', 'description': 'Product marketplace and shopping endpoints'},
    ],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,  # Persist authorization token in browser
        'displayRequestDuration': True,
        'filter': True,
        'showExtensions': True,
        'showCommonExtensions': True,
        'tryItOutEnabled': True,
    },
    'SWAGGER_UI_FAVICON_HREF': '/static/favicon.ico',
    'REDOC_UI_SETTINGS': {
        'hideDownloadButton': False,
        'expandResponses': '200,201',
        'pathInMiddlePanel': True,
    },
    'AUTHENTICATION_WHITELIST': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
    'SECURITY': [{'BearerAuth': []}],
}

