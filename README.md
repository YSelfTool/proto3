# Protokollsystem 3

System zur Verwaltung von Protokollen und Sitzungen.

* Planung der Tagesordnung
* Einladungsmails
* Kompilieren vom Protokollquelltext
* PDF-Protokoll mit LaTeX
* Protokollversand samt Anhang
* automatisches Hochladen ins Wiki
* Etherpadanbindung
* Todoverwaltung mit mehr Zuständen
* Beschlussverwaltung
* Rechteverwaltung (interne Abschnitte)
* Hochladen der Tagesordnung in einen Kalender
* externe Protokolle ohne Protokollsyntax

# HowTo Setup

Required infrastructure:

* some WSGI-capable webserver (nginx + uwsgi, …)
* some database (postgres, …)
* some LDAP server (Samba 4, slapd, …) for accounts and groups
* texlive
* some message broker for [celery](http://docs.celeryproject.org/en/latest/getting-started/brokers/) (redis, …)

Optional infrastructure:

* a mail server (for sending protocols and invitations)
* a CUPS printing server (for printing protocols and decisions)
* an [Etherpad](https://github.com/ether/etherpad-lite) (for writing the protocol collectively)
* a Mediawiki instance (for uploading the protocols there)
* a CalDAV server (for uploading the events)

Steps:

1. clone the [repository](https://git.fsmpi.rwth-aachen.de/protokollsystem/proto3)
2. create a python virtualenv and install the packages from `requirements.txt` there
3. create a database (tested with postgres and sqlite, but feel free to use whatever you like and [SQLAlchemy](http://docs.sqlalchemy.org/en/latest/dialects/index.html) supports
4. copy `config.py.example` to `config.py` and edit it
  * **do** change everything commented with `change this`
  * do **not** change the lines commented with `do not change`
  * deactivate unwanted features with `SOMETHING_ACTIVE = False`
  * if you want to use a feature, set the connection configuration lines accordingly
  * define a list of authentication backends (usually one):
    - use LdapManager for slapd
    - use ADManager for Samba
    - write your own for anything else (see `auth.py`, just the methods `authenticate` and `groups` are required)
  * define the available printers (if wanted) with a list of options they should use (see lpoptions)
  * if you do not know what a MediaWiki-domain is, you probably don't need it
  * fix the path to the fonts (and select which to use)
  * most points should be documented in the example config
5. create the database schema with `./server.py db upgrade`
6. configure your server to run the wsgi-application and the celery-server
  * if you use systemd, example service files are located in `example-config/` in this repository
7. configure your webserver to serve the wsgi-application
  * if you use uwsgi+nginx, example config if located in `example-config/`
  * don't forget to pass the correct IP if you use some proxy-setup and want to use IP-based access per protocol type
8. Test if it is working properly
