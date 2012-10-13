from .settings import *

# don't repeat connection OPTIONS here, the database server behavior needs to be the same in 
# development
DATABASES['default']['NAME'] = '{{ project_name }}_prod'

INSTALLED_APPS += (
    'debug_toolbar',
)

MIDDLEWARE_CLASSES = (
    'debug_toolbar.middleware.DebugToolbarMiddleware',
) + MIDDLEWARE_CLASSES