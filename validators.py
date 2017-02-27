from models.database import TodoState
from wtforms import ValidationError
from wtforms.validators import InputRequired
from shared import db

class CheckTodoDateByState:
    def __init__(self):
        pass

    def __call__(self, form, field):
        try:
            todostate = TodoState(field.data)
            if todostate.needs_date():
                date_check = InputRequired("Dieser Status benötigt ein Datum.")
                form.date.errors = []
                date_check(form, form.date)
        except ValueError:
            raise ValidationError("Invalid state.")

