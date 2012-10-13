=======================
     project skel
=======================

This skeleton gives you a complete Fabric deployment and development toolchain with 
it's main goal beeing convenience.

It bundles a django project template with couple minor changed from the 1.4 default: adjusted 
MEDIA_ROOT/STATIC_ROOT and some additional variables for common paths for the project. 

Features
========

* **ready made system** - you can deploy it to an ubuntu 12.04 server right after running startproject
* **versioned deployments** - errors during a deployment will rollback it
* **bundled dependencies** - the deployed archive contains the dependencies - no more broken deployments because some random pypi downtime
* **mulitenacy** - you can deploy multiple instances (as fabric roles) of the project on the same server

Beyond those features listed above this skel does few choices for you:

* configuration is versioned because it's inside the project. This is a choice of 
  convenience over best practice. If you don't want this you can change the fabfile.py to load
  configuration from external files (that you store in a "well known location").
* no access to the git/hg repository from the servers. The sources are zipped and 
  uploaded to the server instead. This is one one hand a security boost and on the other 
  a convenience (less configuration and you don't really need to have good branching strategies).  
* everything is deployed in the user home directory. Only few changes are made to the apache/supervisord 
  config to make them load additional configuration form the user's home directory. This is to 
  encourage isolation for the daemons you run on the server and make it easy to use this with
  minor changes on shared hosting or other linuxes (like centos, fedora etc).


Complete list of commands
=========================

* **bootstrap** -Setup a working environment locally.
* **build** - Make a build of the current revision in .build directory.
* **bundlestrap** - Bootstrap the uploaded project package on the remote server.
* **check_dependency_updates** - Check for dependency updates in the local development environment.
* **clean** - Remove existing virtualenv and builds.
* **cleanup_pyc** - Removes \*.pyc and \*.pyo files.
* **deploy** - Deploy the current revision.
* **django_admin**
* **django_startproject**
* **download**
* **environment** - Use a specific config set (environment).
* **fab** - Run a remove fab command in the currently installed project's root.
* **m** - manage.py shorthand. Eg: `fab m:syncdb`
* **makemessages** - Run manage.py makemessages. Eg: `fab makemessages:ro,fr,ru`
* **manage**
* **prune_builds** - Remove old builds from the remove system.
* **reset_db** - Reset database and recreate it. Requires django-extensions.
* **run** - Run the dev server, eg: `fab run:ip:port`, `fab run`
* **run_tmux** - Start tmux session with panes for `left_commands` and `right_commands`.
* **runex** - Start tmux session with panes for celeryd, runserver, celerycam, tail postgresql log. This is just an example.
* **setup_db** - Setup *empty* database (aka syncdb --all and migrate --fake).
* **setup_postgresql** - Setup postgresql on the remote server.
* **shell** - Run command in a remote shell (in ./~).
* **sloc** - Compute SLOC report using metrics.
* **sloccount** - Compute SLOC report using sloccount.
* **sudoshell** - Sudo run command in a remote shell (in ./~).
* **update_dependency** - Update specific or all dependencies in the local environment. Eg: `fab update_dependency:celery`, `fab update_dependency`
* **upload** - Upload the built project package to the remote server.
* **version** - Display the current version of the package.



Setting up the project
======================

Requirements
------------

Core requirements:

- ubuntu 12.04 (probably works on older)
- fabric 1.4
- python 2.7
- setuptools
- pip
- virtualenv
- hg-describe (if you're using mercurial)


To install them on ubuntu/debian run::

    sudo apt-get install python-setuptools build-essential python-dev
    sudo easy_install -U pip virtualenv
    sudo pip install -U Fabric

If you're using mercurial::

    pip install https://bitbucket.org/Almad/hg-describe/get/default.zip
    add "hgdescribe =" in ~/.hgrc [extensions]

Creating myproject on the empty projectskel
-------------------------------------------

Projectskel comes with an empty src dir - you have to create the project youself
using django-admin.py.

Edit fabfile.py to have::

    settings.project_name = 'myproject'

For django 1.4 you have to run::

    fab bootstrap
    fab django_startproject

To add new apps::

    cd src
    fab django_admin:"startapp mydjangoapp"


Local development setup (optional)
----------------------------------

If you want to run the project localy with postgresql server::

    sudo apt-get install postgresql-9.1 python-psycopg2

The postgresql server needs few basic settings: in
/etc/postgresql/9.1/main/pg_hba.conf add "local all all trust" and then run::

    /etc/init.d/postgresql restart
    sudo -u postgres createuser -R -S -d `echo $USER`
    createdb myproject

Then edit settings_local.py to match the database name.

Deployment and configuration
============================

The project has a "role" for each type of server (like a webserver or a type of
worker). There can be serveral types of workers for each set of server
credentials (username, password).

A role is composed of configuration in several places in the project:

- in src/myproject/ there a settings file for each role.
- in fabfile.py there a list of servers assigned to a role (search for
  env.roledefs)
- in fabfile.py there an additional dictionary with settings for each role
  (search for env.roleconfig) that coulbe be used in the deployment templates (dist/templates)

To add a new role you need to add new configuration in each of the 3 places
described above. If you just have a new server that's identical to existing
servers then just add it in the env.roleconfig list for the correct role.

.. warning:: 

    Role name must not contain spaces !

To deploy the aplication to on servers from a specific role just run::

    fab -R rolename -u username -p password deploy
