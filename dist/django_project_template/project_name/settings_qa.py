from .settings import *

# don't repeat connection OPTIONS here, the database server behavior needs to be the same in 
# development
DATABASES['default']['NAME'] = '{{ project_name }}_qa'
