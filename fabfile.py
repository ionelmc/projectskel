# -*- coding: utf-8 -*-
from __future__ import with_statement
from __future__ import division

import os
import sys
import time

from fabric import operations as ops, context_managers as ctx
from fabric.api import env, task
from fabric.contrib import files
from fabric import colors
from fabutil import *

#settings.py_version = 'python%s.%s-dbg' % (sys.version_info[0], sys.version_info[1])
settings.project_name = 'myproject'
#settings.build_ignore_file_patterns = [
#    'resources', 
#    'dist/templates', 
#    '.komodotools'
#]

env.roledefs = {
    'qa': ['192.168.106.129'],
    'prod': ['192.168.106.129'],
}
env.roleconfig = {
    'qa': {
        'SERVER_NAME': 'mydomain.com',
        'CELERY_WORKER_ARGS': '-Q default -c 6 -E',
        'HTTPD_ALIAS': '/qa',
    },
    'prod': {
        'CELERY_WORKER_ARGS': '-Q default -c 6 -E',
    },
}

@task
def run(bind_to="0.0.0.0:8000"):
    """
    Run the dev server, eg: fab run:ip:port; fab run
    """
    manage("syncdb --verbosity=0 --migrate --noinput")
    manage("runserver --verbosity=2 --traceback %s" % bind_to)

@task
def reset_db(noinput=False):
    """
    Reset database and recreate it. Requires django-extensions.
    """
    if noinput or confirm("Really erase database ?"):
        manage("reset_db --noinput --router=default")
        setup_db()

@task
def m(args=''):
    """
    manage.py shorthand. Eg: fab m:syncdb
    """
    manage(args)

@task
def deploy_supervisord(glob_pattern="*", **kwargs):
    config_supervisord(
        glob_pattern=glob_pattern,
        **kwargs
    )()

@task
def deploy_nginx(glob_pattern="*", **kwargs):
    config_nginx(
        glob_pattern=glob_pattern,
        **kwargs
    )()

@task
@require_role
def deploy(what=None, keep=3):
    """
    Deploy the current revision.
    """
    build()
    with ctx.settings(warn_only=True):
        prod_db_backup()
    prune_builds(keep)
    upload()
    bundlestrap()
    setup_postgresql()
    fab('manage:"syncdb --migrate --noinput"', version=prj.build_name)
    fab('manage:"collectstatic --noinput"', version=prj.build_name)

    install(
        rollover_project_link, 
        config_cron(), 
        config_apache()
        # use these instead of apache if you want uwsgi 
        # config_nginx(),
        # config_supervisord(),
    )

    print colors.yellow(" __________________________________________________________")
    print colors.yellow("|                                                          |")
    print colors.yellow("| ") + colors.green("Successfully deployed:") + " "*35 + colors.yellow("|")
    print colors.yellow("|") + "     %s " % colors.green(prj.build_name.ljust(52), bold=True) + colors.yellow("|")
    print colors.yellow("| ") + "To:".ljust(57) + colors.yellow("|")
    print colors.yellow("|") + "     %s " % colors.green(env.host.ljust(52), bold=True) + colors.yellow("|")
    print colors.yellow("| ") + "As:".ljust(57) + colors.yellow("|")
    print colors.yellow("|") + "     %s " % colors.green(env.role.upper().ljust(52), bold=True) + colors.yellow("|")
    print colors.yellow("|__________________________________________________________|")

@task
def setup_db():
    """
    Setup *empty* database (aka syncdb --all and migrate --fake).
    """
    manage("syncdb --all")
    manage("migrate --fake")

@task
@require_role
def prod_db_backup():
    shell("pg_dump --clean -f snapshot.sql --no-owner --no-acl " +
        settings.project_name)
    download("snapshot.sql", "backup-%s.sql" % time.time())

@task
def sloc():
    """
    Compute SLOC report using metrics.
    """
    with ctx.lcd(settings.root_path):
        local(".ve/bin/pip install pygments metrics")
        local('.ve/bin/metrics -v `find \`cat METRICS\` -type f \( '
              '-iname "*.css" -or -iname "*.py" -or -iname "*.js" '
              '-or -iname "*.html" -or -iname "*.txt" '
              '\) \! -path "*/migrations/*.py" -print` ')

@task
def sloccount():
    """
    Compute SLOC report using sloccount.
    """
    if local("dpkg -s sloccount", quiet=True, capture=True).failed:
        local("sudo apt-get install sloccount")
    local('sloccount `find \`cat METRICS\` -type f \( '
               '-iname "*.css" -or -iname "*.py" -or -iname "*.js" '
               '-or -iname "*.html" -or -iname "*.txt" '
               '\) \! -path "*/migrations/*.py" -print` ')

@task
def makemessages(*languages):
    """
    Run manage.py makemessages. Eg: fab makemessages:ro,fr,ru
    """
    for lng in languages:
        manage("makemessages -l "+lng)

@task
def run_tmux(left_commands=(), right_commands=()):
    """
    Start tmux session with panes for `left_commands` and `right_commands`.
    """
    import subprocess
    session = 'tmux set -g mouse-select-pane on;'
    #' tmux setw -g mode-mouse on; '
    #' tmux set-option -g set-remain-on-exit on; '

    if right_commands:
        session += 'tmux selectp -t 0; tmux splitw -hd -p 35 \"%s\"; ' % right_commands[-1]
    for index, command in enumerate(right_commands[:-1]):
        session += 'tmux selectp -t 1; tmux splitw -d -p %i \"%s\"; ' % (
            100 / (len(right_commands) - index),
            command
            )

    for index, command in enumerate(left_commands[1:]):
        session += 'tmux selectp -t 0; tmux splitw -d -p %i \"%s\"; ' % (
            100 / (len(left_commands) - index),
            command
            )
    if left_commands:
        session += left_commands[0]

    args = [
        'tmux',
        'new-session',
        session,
        ]
    print 'Running ', args
    subprocess.call(args)


@task
def runex():
    """
    Start tmux session with panes for celeryd, runserver, celerycam, tail postgresql log. This is just an example.
    """
    run_tmux(
        left_commands=[
            "fab manage:celeryd",
            ],
        right_commands=[
            "fab manage:celerycam",
            "tail -f /var/log/postgresql/postgresql-8.4-main.log",
            "fab run",
            #"htop",
        ]
    )

@task
def install_certificates():
    from glob import glob
    for path in glob('dist/certificates/*'):
        ops.put(path, '/etc/ssl/private/', use_sudo=True)