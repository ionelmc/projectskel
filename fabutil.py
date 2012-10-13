"""
Provides various fabric utilities.
"""
from __future__ import with_statement
__all__ = (
    'settings', 'clean', 'manage', 'require_role', 'bootstrap', 'cleanup_pyc',
    'download', 'sudoshell', 'shell', 'onefab', 'fab', 'version', 'environment',
    'build', 'upload', 'bundlestrap', 'config_apache', 'local',
    'setup_postgresql', 'prune_builds','rollover_project_link', 'prj',
    'config_cron', 'install', 'django_admin', 'update_dependency',
    'check_dependency_updates', 'shell', 'confirm', 'config_supervisord',
    'django_startproject'
)
import hashlib
import hmac
import os
import glob
import re
import sys
import traceback
from contextlib import contextmanager
from functools import wraps
from fabric import operations as ops, context_managers as ctx
from fabric.operations import open_shell
from fabric.api import env, task
from fabric.contrib import files
from fabric.decorators import runs_once
from fabric.contrib.console import confirm
from fabric import colors

try:
    from os.path import relpath
except ImportError:
    from os.path import curdir as _curdir

    def relpath(path, start=_curdir):
        """Return a relative version of a path"""
        from os.path import abspath, commonprefix, join, sep, pardir
        if not path:
            raise ValueError("no path specified")
        start_list = abspath(start).split(sep)
        path_list = abspath(path).split(sep)
        # Work out how much of the filepath is shared by start and path.
        i = len(commonprefix([start_list, path_list]))
        rel_list = [pardir] * (len(start_list) - i) + path_list[i:]
        if not rel_list:
            return _curdir
        return join(*rel_list)

@contextmanager
def cwd(path):
    old_path = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_path)

class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

settings = AttrDict(
    deployment_dir = 'deployed',
    py_version = 'python%s.%s' % (sys.version_info[0], sys.version_info[1]),
    environment = 'local',
    use_distribute = True,
    use_jinja = True,
    build_ignore_file_patterns = ['dist'],
    project_name = 'namelessproject',
    root_path = os.path.abspath(os.path.dirname(__file__)),
    venv_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '.ve'),
)

def require_role(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if len(env.roles) != 1:
            raise RuntimeError("Please specify only a single role!")

        # Call the decorated function
        env.role = env.roles[0]
        return func(*args, **kwargs)

    return wrapper

def local(command, quiet=False, capture=False):
    if quiet:
        with ctx.settings(ctx.hide('aborts', 'warnings'), warn_only=True):
            return ops.local(command, capture=capture)
    else:
        return ops.local(command, capture=capture)

def silentrun(command, use_sudo=False, **kwargs):
    with ctx.settings(ctx.hide('aborts', 'warnings'), warn_only=True):
        return (ops.sudo if use_sudo else ops.run)(command, kwargs)

class cached_property(object):
    def __init__(self, function, name=None):
        self.function = function
        self.name = name or '_%s_cache' % function.__name__

    def __get__(self, inst, _class):
        if inst is None:
            return self
        if hasattr(inst, self.name):
            return getattr(inst, self.name)
        else:
            val = self.function(inst)
            setattr(inst, self.name, val)
            return val

class Project(object):
    @cached_property
    def scm_type(self):
        if os.path.isdir(os.path.join(settings.root_path, '.hg')):
            return 'hg'
        elif os.path.isdir(os.path.join(settings.root_path, '.git')):
            return 'git'
        else:
            raise RuntimeError, "Unknown revision control system. Only git and mercurial are supported."

    @property
    def is_git(self):
        return self.scm_type == 'git'

    @property
    def is_hg(self):
        return self.scm_type == 'hg'

    @cached_property
    def tag(self):
        with ctx.lcd(settings.root_path):
            with ctx.settings(ctx.hide('running')):
                if self.is_hg:
                    t = ops.local('hg describe', capture=True)
                elif self.is_git:
                    t = ops.local('git describe --tags || git rev-parse HEAD',
                                  capture=True)
                else:
                    raise RuntimeError("Unknown revision control system. "
                                       "Cannot extract a tag.")
                return str(t.replace(' ', '-').replace('(', '') \
                        .replace(')', '').replace('+', '-dev').strip())

    @property
    def build_name(self):
        return '%s-%s' % (settings.project_name, self.tag)

    @cached_property
    def requirements_hash(self):
        digest = hmac.new('REQUIREMENTS', digestmod=hashlib.sha1)
        dependencies = []
        source_dependencies = False
        for line in file(os.path.join(settings.root_path, 'REQUIREMENTS')):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('-e'):
                source_dependencies = True
            dependencies.append(line)

        digest.update(';;'.join(sorted(dependencies)))

        if source_dependencies:
            print colors.red('WARNING: You have source dependencies in your '
                             'REQUIREMENTS file !')

        return digest.hexdigest()

prj = Project()

@runs_once
@task
def build(args=''):
    """
    Make a build of the current revision in .build directory.
    """
    with ctx.lcd(settings.root_path), cwd(settings.root_path):
        local('mkdir -p .builds')
        local('mkdir -p .pip-cache')

        # Clean the build?
        if 'clean' == args:
            local('rm -f .builds/project-deps.*')
            local('rm -f .pip-cache/*')

        # Create project-deps.zip (pip bundle) if necessary
        sig_file = '.builds/project-deps.sig'
        if not os.path.exists(sig_file) or \
           prj.requirements_hash != file(sig_file).read():
            local(
                'pip bundle .builds/project-deps.zip -r REQUIREMENTS '
                '--timeout=1 --download-cache=.pip-cache'
            )
            with file(sig_file, 'w') as fh:
                fh.write(prj.requirements_hash)


        # Create the project package
        if getattr(settings, 'build_ignore_file_patterns', None):
            # the cat is a work around buffering issue in tarfile (pipe would get
            # closed before tarfile flushes it's contents at Tarfile.__del__)
            exclude_pipe = (
                '| python -u -c "import sys; sys.stdout.write(sys.stdin.read())" | tar --wildcards --delete ' +
                ' '.join(
                    [os.path.join(prj.build_name, pattern) for pattern in settings.build_ignore_file_patterns]))
        else:
            exclude_pipe = ''

        if prj.is_hg:
            local('hg archive --type=tar --prefix=%s - %s | gzip > .builds/project.tar.gz' % (
                prj.build_name,
                exclude_pipe
            ))
        elif prj.is_git:
            local('git archive --format=tar --prefix=%s/ %s %s | gzip > .builds/project.tar.gz' % (
                prj.build_name,
                prj.tag,
                exclude_pipe
            ))
        else:
            raise RuntimeError, "Unknown revision control system. Cannot build."

        with ctx.lcd('.builds'):
            local('tar czf %s.tar.gz project.tar.gz project-deps.zip' % prj.build_name)
            local('rm -f project.tar.gz')

        # Remove pip's temp dirs
        local('rm -rf build-bundle* src-bundle*')

        # Some output
        print colors.yellow(" ____________________________________________________________________")
        print colors.yellow("|                                                                    |")
        print colors.yellow("|") + " The package was created successfully!                              " + colors.yellow("|")
        print colors.yellow("|") + " You can refer to this package using the following tag:             " + colors.yellow("|")
        print colors.yellow("|") + colors.blue(prj.tag.center(68), bold=True) + colors.yellow("|")
        print colors.yellow("|                                                                    |")
        print colors.yellow("|") + " FILES:                                                             " + colors.yellow("|")
        with ctx.settings(ctx.hide("running", "stdout", "stderr")):
            with ctx.lcd('.builds'):
                for i in ops.local("du -sh *%s*" % prj.tag, capture=True).splitlines():
                    print colors.yellow("| ") + colors.cyan(i.expandtabs()).ljust(76) + colors.yellow("|")
                for i in ops.local("du -sh *project-deps*", capture=True).splitlines():
                    print colors.yellow("| ") + colors.cyan(i.expandtabs()).ljust(76) + colors.yellow("|")
        print colors.yellow("|____________________________________________________________________|")


@task
@require_role
def upload(what=None):
    """
    Upload the built project package to the remote server.
    """
    if what:
        ops.put(what)
    else:
        with ctx.lcd(settings.root_path):
            ops.run('mkdir -p builds')
            # Upload the current package
            fname = "builds/%s.tar.gz" % prj.build_name
            ops.put("." + fname, fname)


@task
@require_role
def bundlestrap():
    """
    Bootstrap the uploaded project package on the remote server.
    """
    ## Install bare server requirements
    if silentrun('which pip').failed:
        ops.sudo('easy_install pip')
    if silentrun('which virtualenv').failed:
        ops.sudo('pip install virtualenv')
    if silentrun('which fab').failed:
        ops.sudo('apt-get install python-dev')
        ops.sudo('pip intall Fabric')
    deployment_dir = '~/%s/%s' % (settings.deployment_dir, env.role)
    ops.run('mkdir -p ' + deployment_dir)
    # temporarily disable .pydistutils.cfg, see https://github.com/pypa/virtualenv/issues/88
    pydistutils = files.exists('.pydistutils.cfg')
    if pydistutils:
        ops.run("mv ~/.pydistutils.cfg ~/.pydistutils.cfg.disabled")

    with ctx.cd(deployment_dir):
        ops.run('rm -rf %s' % prj.build_name)
        ops.run('tar xmzf ~/builds/%s.tar.gz' % prj.build_name)
        ops.run('tar xmzf project.tar.gz')
        ops.run('virtualenv %s/.ve --python=%s --system-site-packages' % (
            prj.build_name, settings.py_version
        ) + ' --distribute' if settings.use_distribute else '')
        ops.run('%s/.ve/bin/pip install -I project-deps.zip' % prj.build_name)
        ops.run('rm -rf %s/.ve/build' % prj.build_name)
        ops.run('rm -f project-deps.zip project.tar.gz')

    with ctx.cd("%s/%s" % (deployment_dir, prj.build_name)):
        ops.run('.ve/bin/python setup.py develop')

    if pydistutils:
        ops.run("mv ~/.pydistutils.cfg.disabled ~/.pydistutils.cfg")

@require_role
@task
def rollover_project_link():
    with ctx.cd('~/%s/%s' % (settings.deployment_dir, env.role)):
        ops.run('rm -f current && ln -s %s current' % prj.build_name)

@task
@require_role
def fab(args='', role=None, version=None):
    "Run a remove fab command in the currently installed project's root."
    with ctx.cd("~/%s/%s/%s" % (settings.deployment_dir, env.role, version or 'current')):
        ops.run("fab environment:%s %s" % (role or env.role, args))

onefab = runs_once(fab)

@task
@require_role
def shell(args=None, path="~/"):
    "Run command in a remote shell (in ./~). If command not specified then run the default shell."
    if args is None:
        open_shell()
    else:
        with ctx.cd(path):
            ops.run(args)

@task
@require_role
def sudoshell(args="bash"):
    "Sudo run command in a remote shell (in ./~)."
    with ctx.cd("~/"):
        ops.sudo(args)

@runs_once
@task
def clean():
    "Remove existing virtualenv and builds."
    with ctx.lcd(settings.root_path):
        local("rm -rf .ve .builds", quiet=True)

@task
def bootstrap(args=''):
    """
    Setup a working environment locally.
    """
    deb_packages = [pkg.strip() for pkg in file("DEB-REQUIREMENTS")
                    if not pkg.startswith('#')]
    if any(
        local("dpkg -s %s" % pkg, quiet=True, capture=True).failed
        for pkg in deb_packages
    ):
        if confirm("Install debian packages (%s) ?" % ', '.join(deb_packages)):
            local("sudo apt-get install `cat DEB-REQUIREMENTS`")

    with ctx.lcd(settings.root_path):
        local("mv .ve .ve-backup", quiet=True)
        if args == 'nocache':
            local("rm -rf .pip-cache", quiet=True)
        try:
            # PIP install requirements
            local("mkdir -p .pip-cache", quiet=True)
            local(
                "virtualenv .ve --system-site-packages "
                "--python=%s" % settings.py_version +
                ' --distribute' if settings.use_distribute else ''
            )
            local(
                ".ve/bin/pip install --download-cache=.pip-cache "
                "-I --source=.ve/src/ %s --timeout=1" % ' '.join(
                    "-r " + i for i in glob.glob("REQUIREMENTS*")
                )
            )

            # install project as a development package (inplace)
            local(".ve/bin/python setup.py develop")
            local("rm -rf .ve-backup")
        except:
            local("mv .ve-backup .ve", quiet=True)
            raise

@task
def python(args):
    local(
        "DJANGO_SETTINGS_MODULE=%(project_name)s.settings_%(environment)s "
        "FLAVOR=%(environment)s %(root_path)s/.ve/bin/python %(args)s" % dict(
            settings,
            args=args
        )
    )

@task
def django_admin(args=''):
    local(
        "DJANGO_SETTINGS_MODULE=%(project_name)s.settings_%(environment)s "
        "FLAVOR=%(environment)s %(root_path)s/.ve/bin/django-admin.py "
        "%(args)s" % dict(
            settings,
            args=args
        )
    )
@task
def django_startproject():
    with ctx.lcd(settings.root_path):
        django_admin(
            "startproject --template=dist/django_project_template %r src" %
            settings.project_name
        )
@task
def manage(args=''):
    python("%s/src/manage.py %s" % (settings.root_path, args))

@task
def cleanup_pyc():
    """
    Removes *.pyc and *.pyo files.
    """
    with ctx.lcd(settings.root_path):
        local("find src -type f -name '*.py[co]' -print0 | xargs -0 rm -f")

@task
def download(what, dest='download'):
    local("mkdir -p download")
    ops.get(what, dest)

@task
def set_python(name):
    """
    Use another version of python. Usage: set_python:python2.4
    """
    settings.py_version = name

@task
def version():
    """
    Display the current version of the package.
    """
    print " __________________________________________________________"
    print "|                                                          |"
    print "| Current version:                                         |"
    print "|  %s |" % colors.white(prj.build_name.center(55), bold=True)
    print "|__________________________________________________________|"

@task
def environment(what):
    """
    Use a specific config set (environment).
    """
    settings.environment = what

@task
@require_role
def prune_builds(keep=3):
    """
    Remove old builds from the remove system.
    """
    try:
        keep = int(keep)
    except:
        raise RuntimeError("prune_builds argument must be integer instead of %r." % keep)

    if keep:
        with ctx.cd('~/%s/%s' % (settings.deployment_dir, env.role)):
            versions = [i for i in silentrun('ls -1t').split() if i.startswith(settings.project_name)]
            for version in versions[keep:]:
                ops.run('rm -rf %s' % version)
                ops.run('rm -f ~/builds/%s.tar.gz' % version)

@task
def check_dependency_updates():
    """
    Check for dependency updates in the local development environment.
    """
    with ctx.lcd(settings.root_path), cwd(settings.root_path):
        local('.ve/bin/pip install yolk')
        reqs = [re.split('[<>=]', line)[0] for line in [
            line.strip() for line in open('REQUIREMENTS')
        ] if not line.startswith('#') #and not '/' in line
        ]

        for req in reqs:
            local('.ve/bin/yolk -U ' + req)

@task
def update_dependency(name=None):
    """
    Update specific or all dependencies in the local environment. Eg: fab update_dependency:celery; fab update_dependency
    """
    with ctx.lcd(settings.root_path), cwd(settings.root_path):
        if name:
            local(".ve/bin/pip install --download-cache=.pip-cache -I --source=.ve/src/ "
                  "--timeout=1 `grep -iP '(?!#).*%s.*' REQUIREMENTS`" % name)
        else:
            local(".ve/bin/pip install --download-cache=.pip-cache -U --source=.ve/src/ "
                  "--timeout=1 -r REQUIREMENTS")

@require_role
def install_config_templates(template_pattern,
                             backup_action,
                             rollback_action,
                             rollover_action,
                             install_action,
                             glob_pattern="*", **extra_template_vars):
    if local('python -c "import jinja2"', quiet=True).failed:
        local('sudo pip install Jinja2')
    caller_name = sys._getframe(4).f_code.co_name

    with ctx.cd("~/"), ctx.lcd(settings.root_path), cwd(settings.root_path):
        home_path = ops.run('pwd').strip()
        template_vars = {
            'USERNAME': env.user,
            'FLAVOR': env.role,
            'PKGNAME': settings.project_name,
            'APPDIR': os.path.join(home_path,
                                   settings.deployment_dir,
                                   env.role,
                                   prj.build_name),
            'USERDIR': home_path,
        }
        template_vars.update(env.roleconfig[env.role])
        template_vars.update(extra_template_vars)

        print colors.blue("Running backup action for %s ..." % caller_name)
        backup_action(**template_vars)

        config_files = []
        for config_file in glob.glob(
            template_pattern % glob_pattern
                if glob_pattern is not None
                else template_pattern):
            print colors.green(
                "Installing %s for %s ..." % (config_file, caller_name)
            )
            config_files.append(install_action(config_file, **template_vars))

        def rollover():
            try:
                print colors.yellow(
                    "Running rollover action for %s ..." % caller_name
                )
                rollover_action(config_files, **template_vars)
            except:
                traceback.print_exc()
                print colors.red(
                    "Unexpected error. Running rollback action for %s ..." %
                    caller_name
                )
                rollback_action(**template_vars)
                raise
        rollover.__name__ = 'rollover_'+caller_name
        rollover.rollback = lambda: rollback_action(**template_vars)
        return rollover

@require_role
def config_supervisord(glob_pattern="*", **kwargs):
    def backup_action(**kwargs):
        if files.exists("%(USERDIR)s/supervisord/conf.d" % kwargs):
            ops.run("rm -rf %(USERDIR)s/supervisord/conf.d-backup" % kwargs)
            ops.run("mkdir %(USERDIR)s/supervisord/conf.d-backup" % kwargs)
            ops.run("cp %(USERDIR)s/supervisord/conf.d/* %(USERDIR)s/supervisord/conf.d-backup" % kwargs)

    def rollback_action(**kwargs):
        ops.run("rm -rf %(USERDIR)s/supervisord/conf.d" % kwargs)
        ops.run("mv %(USERDIR)s/supervisord/conf.d-backup %(USERDIR)s/supervisord/conf.d" % kwargs)

    def rollover_action(config_files, **kwargs):
        ops.sudo("supervisorctl stop all")
        ops.sudo("supervisorctl reread")
        ops.sudo("supervisorctl update")
        ops.sudo("supervisorctl start all")
        ops.sudo("supervisorctl status")

    def install_action(config_file, **kwargs):
        kwargs['CONFIGNAME'] = os.path.splitext(os.path.basename(config_file))[0]
        conf_path = "%(USERDIR)s/supervisord/conf.d/%(CONFIGNAME)s-%(PKGNAME)s-%(FLAVOR)s.conf" % kwargs
        ops.run("mkdir -p %(USERDIR)s/supervisord/conf.d" % kwargs)
        files.upload_template(config_file, conf_path, kwargs, use_jinja=settings.use_jinja)
        return "%(PKGNAME)s-%(FLAVOR)s-%(CONFIGNAME)s" % kwargs

    with ctx.cd("~/"):
        home_path = ops.run('pwd').strip()
        if silentrun("dpkg -s supervisor > /dev/null").failed:
            ops.sudo("apt-get install -qq supervisor")
            if not files.contains(
                '/etc/supervisor/supervisord.conf',
                "files = %s/supervisord/conf.d/*.conf" % home_path
            ):
                files.append(
                    '/etc/supervisor/supervisord.conf',
                    "\n[include]\nfiles = %s/supervisord/conf.d/*.conf\n" % home_path,
                    use_sudo = True
                )

    return install_config_templates(
        'dist/templates/supervisord/%s.*',
        backup_action,
        rollback_action,
        rollover_action,
        install_action,
        environment=environment,
        glob_pattern=glob_pattern,
        **kwargs
    )

@require_role
def config_apache(glob_pattern="*", **kwargs):
    def backup_action(**kwargs):
        if files.exists("%(USERDIR)s/httpd/conf.d" % kwargs):
            ops.run("rm -rf %(USERDIR)s/httpd/conf.d-backup" % kwargs)
            ops.run("mkdir %(USERDIR)s/httpd/conf.d-backup" % kwargs)
            ops.run("cp %(USERDIR)s/httpd/conf.d/*"
                    "   %(USERDIR)s/httpd/conf.d-backup" % kwargs)

    def rollback_action(**kwargs):
        ops.run("rm -rf %(USERDIR)s/httpd/conf.d" % kwargs)
        ops.run("mv %(USERDIR)s/httpd/conf.d-backup"
                "   %(USERDIR)s/httpd/conf.d" % kwargs)

    def rollover_action(config_files, **kwargs):
        ops.sudo("apache2ctl configtest")
        ops.sudo("apache2ctl restart")

    def install_action(config_file, **kwargs):
        kwargs['CONFIGNAME'], kwargs['CONFIGTYPE'] = os.path.splitext(os.path.basename(config_file))
        conf_path = "%(USERDIR)s/httpd/conf.d/%(CONFIGNAME)s-%(PKGNAME)s-%(FLAVOR)s%(CONFIGTYPE)s" % kwargs
        if kwargs['CONFIGTYPE'] == '.conf':
            kwargs['WSGIPATH'] = conf_path.replace(".conf", ".wsgi")
        ops.run("mkdir -p %(USERDIR)s/httpd/conf.d" % kwargs)
        files.upload_template(config_file, conf_path, kwargs, use_jinja=settings.use_jinja)

    with ctx.cd("~/"):
        home_path = ops.run('pwd').strip()
        if silentrun("dpkg -s libapache2-mod-wsgi > /dev/null").failed:
            ops.sudo(
                "apt-get install -qq apache2-mpm-worker libapache2-mod-wsgi",
            )
            ops.sudo("a2enmod headers")
            ops.sudo("a2enmod wsgi")
        if not files.contains(
            '/etc/apache2/apache2.conf',
            "Include %s/httpd/conf.d/*.conf" % home_path,
        ):
            files.append(
                '/etc/apache2/apache2.conf',
                "\nInclude %s/httpd/conf.d/*.conf\n" % home_path,
                use_sudo=True
            )

    return install_config_templates(
        'dist/templates/httpd/%s.*',
        backup_action,
        rollback_action,
        rollover_action,
        install_action,
        environment=environment,
        glob_pattern=glob_pattern,
        **kwargs
    )

@task
@require_role
def setup_postgresql():
    """
    Setup postgresql on the remote server.
    """
    if silentrun("dpkg -s postgresql-9.1 > /dev/null").failed:
        ops.sudo("apt-get install postgresql-9.1")
        files.append('local all all trust',
                     '/etc/postgresql/9.1/main/pg_hba.conf', use_sudo=True)
        ops.sudo("/etc/init.d/postgresql restart")
        with ctx.settings(warn_only=True):
            ops.sudo("sudo -u postgres createuser -R -S -d " + env.user)
    with ctx.settings(warn_only=True):
        ops.run("createdb %s_%s" % (settings.project_name, env.role))
    if silentrun("dpkg -s python-psycopg2 > /dev/null").failed:
        ops.sudo("apt-get install python-psycopg2")

@require_role
def config_cron(**kwargs):
    def backup_action(**kwargs):
        with ctx.settings(warn_only=True):
            ops.run("crontab -l 1> %(USERDIR)s/crontab.backup" % kwargs)

    def rollback_action(**kwargs):
        ops.run("crontab %(USERDIR)s/crontab.backup" % kwargs)

    def rollover_action(_config_files, **kwargs):
        ops.run("crontab %(USERDIR)s/crontab.current" % kwargs)

    def install_action(config_file, **kwargs):
        files.upload_template(config_file,
                              "%(USERDIR)s/crontab.current" % kwargs,
                              kwargs,
                              use_jinja=settings.use_jinja)

    return install_config_templates(
        'dist/templates/crontab',
        backup_action,
        rollback_action,
        rollover_action,
        install_action,
        environment=environment,
        glob_pattern=None,
        **kwargs
    )

@require_role
def config_nginx(glob_pattern="*", **kwargs):
    def backup_action(**kwargs):
        if files.exists("%(USERDIR)s/nginx/conf.d" % kwargs):
            ops.run("rm -rf %(USERDIR)s/nginx/conf.d-backup" % kwargs)
            ops.run("mkdir %(USERDIR)s/nginx/conf.d-backup" % kwargs)
            ops.run("cp %(USERDIR)s/nginx/conf.d/*"
                    "   %(USERDIR)s/nginx/conf.d-backup" % kwargs)

    def rollback_action(**kwargs):
        ops.run("rm -rf %(USERDIR)s/nginx/conf.d" % kwargs)
        ops.run("mv %(USERDIR)s/nginx/conf.d-backup"
                "   %(USERDIR)s/nginx/conf.d" % kwargs)

    def rollover_action(config_files, **kwargs):
        ops.sudo("service nginx configtest")
        ops.sudo("service nginx reload")

    def install_action(config_file, **kwargs):
        kwargs['CONFIGNAME'], kwargs['CONFIGTYPE'] = os.path.splitext(os.path.basename(config_file))
        conf_path = "%(USERDIR)s/nginx/conf.d/%(CONFIGNAME)s-%(PKGNAME)s-%(FLAVOR)s%(CONFIGTYPE)s" % kwargs
        if kwargs['CONFIGTYPE'] == '.conf':
            kwargs['WSGIPATH'] = conf_path.replace(".conf", ".wsgi")
        ops.run("mkdir -p %(USERDIR)s/nginx/conf.d" % kwargs)
        files.upload_template(config_file, conf_path, kwargs, use_jinja=settings.use_jinja)

    with ctx.cd("~/"):
        home_path = ops.run('pwd').strip()
        if silentrun("dpkg -s uwsgi-plugin-python > /dev/null").failed:
            ops.sudo(
                "apt-get install -qq uwsgi-plugin-python",
            )
        if silentrun("dpkg -s nginx > /dev/null").failed:
            ops.sudo(
                "apt-get install -qq nginx",
            )
        if not files.contains(
            '/etc/nginx/nginx.conf',
            "http { include %s/nginx/conf.d/*.conf; }" % home_path,
        ):
            files.append(
                '/etc/nginx/nginx.conf',
                "\nhttp { include %s/nginx/conf.d/*.conf; }\n" % home_path,
                use_sudo=True
            )
        if files.exists('/etc/nginx/sites-enabled/default'):
            ops.sudo("rm /etc/nginx/sites-enabled/default")

    return install_config_templates(
        'dist/templates/nginx/%s.*',
        backup_action,
        rollback_action,
        rollover_action,
        install_action,
        environment=environment,
        glob_pattern=glob_pattern,
        **kwargs
    )

def install(*actions):
    ran = []

    print colors.yellow('Running rollover actions:'), colors.magenta([a.__name__ for a in actions])
    for action in reversed(actions):
        try:
            action()
            ran.append(action)
        except:
            print colors.red('Rolling back: %s' % [a.__name__ for a in ran])
            for act in ran:
                act.rollback()
            raise
