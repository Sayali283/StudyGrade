"""
Django settings for smartstudy project.
StudyGrade — AI-Powered Active Recall & Student Mastery Platform.
"""
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from decouple import config
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==============================================================================
# Security & Environment Configuration
# ==============================================================================

import sys
IS_TESTING = 'test' in sys.argv
IS_COLLECTSTATIC = 'collectstatic' in sys.argv

# SECURITY WARNING: DEBUG defaults to False for safe production deployments!
DEBUG = config('DEBUG', default=False, cast=bool)

# SECRET_KEY Management
SECRET_KEY = config('SECRET_KEY', default=None)
if not SECRET_KEY:
    if DEBUG or IS_COLLECTSTATIC or IS_TESTING:
        # Permitted for local development, test runners, and build-time asset collection only
        SECRET_KEY = 'django-insecure-dev-studygrade-local-development-key-only-not-for-prod'
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable must be explicitly configured in production when DEBUG=False."
        )
elif not DEBUG and not IS_TESTING and (
    len(SECRET_KEY) < 24
    or SECRET_KEY.startswith('django-insecure-')
    or SECRET_KEY in {'dev-secret-key-change-me', 'replace-with-a-unique-secret-key-in-production'}
):
    raise ImproperlyConfigured(
        "Insecure SECRET_KEY detected in production. Please configure a unique, random 24+ character key."
    )

# Hostnames & Trusted Domains
allowed_hosts_raw = config(
    'ALLOWED_HOSTS',
    default='' if not DEBUG else 'localhost,127.0.0.1,testserver'
)
if allowed_hosts_raw:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_raw.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = ['studygrade.onrender.com', '.onrender.com'] if not DEBUG else ['localhost', '127.0.0.1']

if 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

csrf_origins_raw = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://studygrade.onrender.com,https://*.onrender.com' if not DEBUG else 'http://localhost:8000,http://127.0.0.1:8000'
)
CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_origins_raw.split(',') if o.strip()]

# HTTPS & Cookie Security Headers
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
    SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_SSL_REDIRECT = False

# ==============================================================================
# Application Definition
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'smartstudy.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'smartstudy.wsgi.application'

# ==============================================================================
# Database Configuration
# ==============================================================================

DATABASE_URL = config('DATABASE_URL', default=None)
USE_SQLITE = config('USE_SQLITE', default=None)

if DATABASE_URL:
    parsed_db = urlparse(DATABASE_URL)
    db_options = {}
    query_params = parse_qs(parsed_db.query)
    if 'sslmode' in query_params:
        db_options['sslmode'] = query_params['sslmode'][0]
    elif not DEBUG:
        db_options['sslmode'] = 'require'

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': unquote(parsed_db.path.lstrip('/')),
            'USER': unquote(parsed_db.username or ''),
            'PASSWORD': unquote(parsed_db.password or ''),
            'HOST': parsed_db.hostname,
            'PORT': parsed_db.port or 5432,
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=600, cast=int),
            'OPTIONS': db_options,
        }
    }
elif USE_SQLITE is False or (USE_SQLITE is None and not DEBUG and not IS_COLLECTSTATIC and not IS_TESTING):
    db_name = config('DB_NAME', default=None)
    if db_name:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': db_name,
                'USER': config('DB_USER', default='postgres'),
                'PASSWORD': config('DB_PASSWORD', default=''),
                'HOST': config('DB_HOST', default='localhost'),
                'PORT': config('DB_PORT', default='5432'),
                'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=600, cast=int),
            }
        }
    else:
        raise ImproperlyConfigured(
            "Production requires a PostgreSQL database. Please configure DATABASE_URL or set USE_SQLITE=True explicitly."
        )
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ==============================================================================
# Storage & Upload Limits
# ==============================================================================

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if IS_TESTING else "core.storage.SafeWhiteNoiseStorage",
    },
}

# Optional S3-compatible Object Storage (AWS S3, Cloudflare R2, MinIO)
USE_S3_STORAGE = config("USE_S3_STORAGE", default=False, cast=bool)
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")

if USE_S3_STORAGE or AWS_STORAGE_BUCKET_NAME:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "access_key": config("AWS_ACCESS_KEY_ID", default=""),
            "secret_key": config("AWS_SECRET_ACCESS_KEY", default=""),
            "region_name": config("AWS_S3_REGION_NAME", default="us-east-1"),
            "endpoint_url": config("AWS_S3_ENDPOINT_URL", default=None),
            "default_acl": "private",
            "file_overwrite": False,
            "querystring_auth": True,
            "querystring_expire": 3600,
        },
    }

# File Upload and Per-User Quota Limits
MAX_UPLOAD_SIZE_BYTES = config('MAX_UPLOAD_SIZE_BYTES', default=10 * 1024 * 1024, cast=int)    # 10 MB per document
MAX_USER_STORAGE_BYTES = config('MAX_USER_STORAGE_BYTES', default=50 * 1024 * 1024, cast=int)  # 50 MB total per student

# ==============================================================================
# Password Validation
# ==============================================================================

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

# ==============================================================================
# Internationalization
# ==============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")

# Authentication redirects
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'student_dashboard'
LOGOUT_REDIRECT_URL = 'home'

# ==============================================================================
# Structured Logging Configuration
# ==============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {process:d} {thread:d}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': config('APP_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}
