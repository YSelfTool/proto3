# Development Guide

## Setup

* Install python3 and virtualenv
* Create a virtualenv and install the requirements

```
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
```

* Create a database (with sqlite, postgres, …)
* Create a config file

```
cp config.py.example config.py
```

* Edit the config file to your needs
  - Don't forget to enter your database connection
  - And your authentication backend
  - And deactivate everything you do not use

* Fill your database

```
./server.py db upgrade
```

## Running the program

```
source venv/bin/activate
./server.py runserver
```

The website will run on `localhost:5000`.


