import os

# This will activate the virtualenv. See activate_this file for more info.
path_to_activate = '{{APPDIR}}/.ve/bin/activate_this.py'
execfile(path_to_activate, dict(__file__=path_to_activate))

# Now we need to configure the actual wsgi application
os.environ['FLAVOR'] = '{{FLAVOR}}'
os.environ['DJANGO_SETTINGS_MODULE'] = '{{PKGNAME}}.settings_{{FLAVOR}}'

import django.core.handlers.wsgi
#from werkzeug.debug import DebuggedApplication
#_application = DebuggedApplication(django.core.handlers.wsgi.WSGIHandler(), evalex=True)
application = django.core.handlers.wsgi.WSGIHandler()
