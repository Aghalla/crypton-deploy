"""
Django settings for the Crypto AI Trading Assistant project.

Development database is SQLite; setting DATABASE_URL (or ENGINE/NAME env vars)
allows switching to PostgreSQL without code changes.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-insecure-key-change-me')
DEBUG = os.getenv('DEBUG', '1') == '1'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '*').split(',') if h.strip()]

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'daphne',  # must come first so runserver uses ASGI
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'channels',
    # project apps
    'apps.core',
    'apps.market_data',
    'apps.analysis',
    'apps.strategies',
    'apps.signals',
    'apps.learning',
    'apps.paper_trading',
    'apps.notifications',
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ---------------------------------------------------------------------------
# Database (SQLite by default, PostgreSQL-ready)
# ---------------------------------------------------------------------------
if os.getenv('DATABASE_ENGINE'):
    DATABASES = {
        'default': {
            'ENGINE': os.getenv('DATABASE_ENGINE'),
            'NAME': os.getenv('DATABASE_NAME', BASE_DIR / 'db.sqlite3'),
            'USER': os.getenv('DATABASE_USER', ''),
            'PASSWORD': os.getenv('DATABASE_PASSWORD', ''),
            'HOST': os.getenv('DATABASE_HOST', ''),
            'PORT': os.getenv('DATABASE_PORT', ''),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # timeout makes concurrent worker threads wait instead of failing
            # with "database is locked".
            'OPTIONS': {
                'timeout': 60,
            },
        }
    }

# ---------------------------------------------------------------------------
# Channels — in-process channel layer (worker threads live inside the same
# process as the ASGI server when WORKER_AUTOSTART is enabled, so no Redis
# is required in development).
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'fa'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# ---------------------------------------------------------------------------
# Project-specific settings
# ---------------------------------------------------------------------------
# Market data
BINANCE_BASE_URL = os.getenv('BINANCE_BASE_URL', 'https://api.binance.com')
BINANCE_PROXY = os.getenv('BINANCE_PROXY', '')  # e.g. http://127.0.0.1:7890
DEMO_MODE = os.getenv('DEMO_MODE', '0') == '1'  # synthetic data when API is unreachable

# AI / learning
AI_MODELS_DIR = Path(os.getenv('AI_MODELS_DIR', BASE_DIR / 'ai_models'))
AI_RETRAIN_THRESHOLD = int(os.getenv('AI_RETRAIN_THRESHOLD', '25'))  # new live samples before retrain
HISTORY_DAYS = int(os.getenv('HISTORY_DAYS', '45'))  # days of 5m history used for initial training

# Worker
WORKER_AUTOSTART = os.getenv('WORKER_AUTOSTART', '1') == '1'  # start worker threads inside runserver
PRICE_UPDATE_SECONDS = int(os.getenv('PRICE_UPDATE_SECONDS', '10'))
CANDLE_UPDATE_SECONDS = int(os.getenv('CANDLE_UPDATE_SECONDS', '60'))
ANALYSIS_INTERVAL_SECONDS = int(os.getenv('ANALYSIS_INTERVAL_SECONDS', '300'))
MONITOR_INTERVAL_SECONDS = int(os.getenv('MONITOR_INTERVAL_SECONDS', '30'))

# Paper trading
PAPER_TRADE_ENABLED = os.getenv('PAPER_TRADE_ENABLED', '1') == '1'

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', '1') == '1'
PAPER_TRADE_TIMEOUT_FACTOR = 2.0  # close a paper trade after holding_time * factor

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'loggers': {
        'crypton': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}

# SQLite WAL mode via connection_created signal
import config.db_signals  # noqa: E402, F401
