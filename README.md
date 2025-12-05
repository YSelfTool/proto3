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

* python >= 3.9
* a pyproject.toml tool (suggested choice: uv)
* some WSGI-capable webserver (nginx + uwsgi, …)
* some database (postgres, …)
* some LDAP server (Samba 4, slapd, …) for accounts and groups
* some message broker for [celery](http://docs.celeryproject.org/en/latest/getting-started/brokers/) (redis, …)

Optional infrastructure:

* texlive for rendering PDFs
* a mail server (for sending protocols and invitations)
* a CUPS printing server (for printing protocols and decisions)
* an [Etherpad](https://github.com/ether/etherpad-lite) (for writing the protocol collectively)
* a Mediawiki/Dokuwiki/GitLab instance (for uploading the protocols there)
* a CalDAV server (for uploading the events)

Steps:

1. clone the [repository](https://git.fsmpi.rwth-aachen.de/protokollsystem/proto3)
2. run `uv sync`
3. create a database (tested with postgres and sqlite, but feel free to use whatever you like and [SQLAlchemy](http://docs.sqlalchemy.org/en/latest/dialects/index.html) supports
4. create `config.py` with `python configproxy.py create --filename config.py` and edit it (make sure that python version >= 3.5)
  * **do** change everything that is not commented out
  * change commented out settings if they are wrong
  * **do** change the random keys `SECRET_KEY` and `SECURITY_KEY` to something random (although the generated config already uses random values generated with `os.urandom`)
  * deactivate unwanted features with `SOMETHING_ACTIVE = False`
  * define a list of authentication backends (usually one):
    - use LdapManager for slapd
    - use ADManager for Samba
    - write your own for anything else (see `common/auth.py`, the methods `authenticate`, `groups` and `all_groups` are required)
  * *MAIL* requires an SMTP(S) server, optionally with STARTTLS or TLS
  * *PRINTING* requires a CUPS printserver
  * *ETHERPAD* requires an etherpad installation
  * *WIKI* requires a MediaWiki or DokuWiki installation
  * *CALENDAR* requires a CalDAV server
  * fix the path to the fonts (and select which to use)
5. create the database schema with `flask db upgrade`
6. configure your server to run the wsgi-application and the celery-server
  * if you use systemd, example service files are located in `example-config/` in this repository
7. configure your webserver to serve the wsgi-application
  * if you use uwsgi+nginx, example config if located in `example-config/`
  * don't forget to pass the correct IP if you use some proxy-setup and want to use IP-based access per protocol type
8. Test if it is working properly
