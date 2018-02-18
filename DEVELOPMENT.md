# Development Guide

## Setup

* Install python3, virtualenv, redis and a database program (postgres, mysql, sqlite does not work with alembic migrations)
* Create a virtualenv and install the requirements

```sh
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
```

* Create a database (with sqlite, postgres, …)
* Create a config file

```sh
cp config.py.example config.py
```

* Edit the config file to your needs
  - Don't forget to enter your database connection
  - And your authentication backend
  - And deactivate everything you do not use
* create the path where PDFs will be stored (`DOCUMENTS_PATH` in config.py)
* Fill your database

```sh
./server.py db upgrade
```

## Running the program

Run (in two terminals, one for the server and one for celery):

```sh
source venv/bin/activate
./server.py runserver
```
```sh
source venv/bin/activate
./start_celery.sh
```

The website will run on `localhost:5000`.

## Data model

The data model is defined in `models/database.py`.
Each type should inherit from `DatabaseModel` and have a method `get_parent()`, which is responsible for the right management and some magic.

## Server endpoints

The actual websites are defined in `server.py`. They begin with the decorator `@app.route((route)` and return a string, usually through `render_template(template, **parameters)`.
There can be more decorators inbetween `app.route` and the function.
A simple website might look like this:
```python
@app.route("/documentation")
@login_required
def documentation():
    todostates = list(TodoState)
    name_to_state = TodoState.get_name_to_state()
    return render_template("documentation.html", todostates=todostates, name_to_state=name_to_state)
```

### Decorators

* `app.route(route)`: Defines for which URLs this function will be called.
  - The route may contain variables: `"/type/edit/<int:protocoltype:id>"`. These will be passed to the function.
  - Additionally, allowed HTTP methods may be defined: `@app.route("/type/new", methods=["GET", "POST"])`. The default is `GET`, but endpoints for forms require `POST` as well.
* `login_required`: Anonymous users will be redirected to the login page.
* `group_required(group)`: Users without this group will see an error message.
* `db_lookup(DataModel)`: Looks up an element of this type. The route needs to have an argument "{model_name}_id". 
