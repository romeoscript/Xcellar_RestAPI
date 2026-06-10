import dj_database_url

from .base import *

DEBUG = False

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# Database — prefer DATABASE_URL (set by PaaS like Railway/Render), and fall
# back to the individual DB_* variables used by docker-compose.
_db_from_url = dj_database_url.config(conn_max_age=600, ssl_require=False)
if _db_from_url:
    DATABASES = {'default': _db_from_url}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'OPTIONS': {
                'sslmode': os.environ.get('DB_SSLMODE', 'require'),
            },
        }
    }

# Security Settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

CSRF_TRUSTED_ORIGINS = ['https://xcellarrestapi-production.up.railway.app']

# Cache + rate limiting. Use Redis (shared across instances) when REDIS_URL is
# set, so login/OTP rate limiting is enforced. Falls back to local-memory cache
# with rate limiting disabled when Redis isn't configured.
REDIS_URL = os.environ.get('REDIS_URL')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
        }
    }
    RATELIMIT_ENABLE = True
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }
    RATELIMIT_ENABLE = False

# Session - database-backed (independent of the cache backend)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Celery - Disable Redis broker/backend (Redis not available)
CELERY_BROKER_URL = None
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = True  # Run tasks synchronously

# Static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files - Serve using WhiteNoise in production
# Note: Railway's filesystem is ephemeral. Files will be lost on container restart.
# For persistent media storage, consider using AWS S3 or Cloudinary.
WHITENOISE_USE_FINDERS = True

# Ensure media directory exists (used only when object storage is not configured)
import os as os_module
MEDIA_ROOT_PATH = os_module.path.join(BASE_DIR, 'media')
if not os_module.path.exists(MEDIA_ROOT_PATH):
    os_module.makedirs(MEDIA_ROOT_PATH, exist_ok=True)

# Media files — use S3-compatible object storage (MinIO / R2 / S3) when a bucket
# is configured, so user uploads (KYC docs, parcel images) survive restarts.
# Falls back to the local filesystem above when AWS_STORAGE_BUCKET_NAME is unset.
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
if AWS_STORAGE_BUCKET_NAME:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    # MinIO requires path-style addressing; private files via presigned URLs.
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_QUERYSTRING_AUTH = os.environ.get('AWS_QUERYSTRING_AUTH', 'True') == 'True'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
