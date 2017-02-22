from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import InputRequired

class LoginForm(FlaskForm):
    username = StringField("User", validators=[InputRequired("Please input the username.")])
    password = PasswordField("Password", validators=[InputRequired("Please input the password.")])
