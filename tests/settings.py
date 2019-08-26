import os

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'tests',
]

SECRET_KEY = "test"

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'sqlite.db',
        # Make in memory sqlite test db to work with threads
        # See https://code.djangoproject.com/ticket/12118
        'TEST': {
            'NAME': ':memory:cache=shared'
        }
    },
}
