from .settings import *

# don't repeat connection OPTIONS here, the database server behavior needs to be the same in
# development
DATABASES['default']['NAME'] = '{{ project_name }}'

INSTALLED_APPS += (
    'debug_toolbar',
)

MIDDLEWARE_CLASSES = (
    'debug_toolbar.middleware.DebugToolbarMiddleware',
) + MIDDLEWARE_CLASSES

DEBUG_TOOLBAR_CONFIG = {
    'INTERCEPT_REDIRECTS': False,
    'SHOW_TOOLBAR_CALLBACK': lambda request: True,
    'HIDE_DJANGO_SQL': False,
    'ENABLE_STACKTRACES' : True,
}