#!/usr/bin/env python3
import os
import unittest
import tempfile
import server as proto3
from flask_migrate import upgrade as db_upgrade
from models.database import ProtocolType, Protocol, DefaultTOP, TOP, Document, DecisionDocument, TodoState, Todo, Decision, MeetingReminder, Error, TodoMail, OldTodo, DefaultMeta, Meta

import sqlite3

def _create_db(sql_script, database_file):
    connection = sqlite3.connect(database_file)
    with open(sql_script, "r") as script_file:
        connection.executescript(script_file.read())
    connection.close()

def _upgrade_db(program_dir):
    migrations_path = os.path.join(program_dir, "migrations")
    db_upgrade(directory=migrations_path)

class GeneralTestCase(unittest.TestCase):
    def _general_setup(self):
        self.program_dir = os.getcwd()
        proto3.app.config["TESTING"] = True
        self.app = proto3.app.test_client()

    def _create_tempdir(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.chdir(self.tempdir.name)

    def _create_db(self, script_name):
        self.database_file = "{}/{}".format(self.tempdir.name, "test-db.sqlite")
        _create_db(os.path.join(self.program_dir, "dbdumps", "{}.sql".format(script_name)), self.database_file)
        proto3.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///{}".format(self.database_file)
        with proto3.app.app_context():
            _upgrade_db(self.program_dir)
        
    def _general_teardown(self):
        self.tempdir.cleanup()
        os.chdir(self.program_dir)
        
    def setUp(self):
        pass

    def tearDown(self):
        pass

STATUS_OK = 200
STATUS_REDIRECT = 302
STATUS_METHOD = 405

class FullDBAnonymousTestCase(GeneralTestCase):
    EXPECTED_SIMPLE_RESULTS = {
        "/": (STATUS_OK, STATUS_METHOD),
        "/documentation": (STATUS_REDIRECT, STATUS_METHOD),
        "/types/list": (STATUS_REDIRECT, STATUS_METHOD),
        "/protocols/list": (STATUS_OK, STATUS_METHOD),
        "/todos/list": (STATUS_REDIRECT, STATUS_METHOD),
        "/decisions/list": (STATUS_OK, STATUS_METHOD),
        "/errors/list": (STATUS_REDIRECT, STATUS_METHOD),
        "/todomails/list": (STATUS_REDIRECT, STATUS_METHOD),
        "/login": (STATUS_OK, STATUS_OK),
        "/logout": (STATUS_REDIRECT, STATUS_METHOD),
    }

    def setUp(self):
        self._general_setup()
        self._create_tempdir()
        self._create_db("full")

    def tearDown(self):
        self._general_teardown()

    def test_simple_status(self):
        for route in self.EXPECTED_SIMPLE_RESULTS:
            get_result = self.app.get(route)
            post_result = self.app.post(route)
            expected_get, expected_post = self.EXPECTED_SIMPLE_RESULTS[route]
            assert get_result.status_code == expected_get
            assert post_result.status_code == expected_post

    def test_protocoltypes(self):
        with proto3.app.app_context():
            new_route = "/type/new"
            assert self.app.get(new_route).status_code == STATUS_REDIRECT
            assert self.app.post(new_route).status_code == STATUS_REDIRECT
            protocoltypes = ProtocolType.query.all()
            for protocoltype in protocoltypes:
                show_route = "/type/show/{}".format(protocoltype.id)
                assert self.app.get(show_route).status_code == STATUS_REDIRECT
                assert self.app.post(show_route).status_code == STATUS_METHOD
                edit_route = "/type/edit/{}".format(protocoltype.id)
                assert self.app.get(edit_route).status_code == STATUS_REDIRECT
                assert self.app.post(edit_route).status_code == STATUS_REDIRECT
                delete_route = "/type/delete/{}".format(protocoltype.id)
                assert self.app.get(delete_route).status_code == STATUS_REDIRECT
                assert self.app.post(delete_route).status_code == STATUS_METHOD
                new_reminder_route = "/type/reminders/new/{}".format(protocoltype.id)
                assert self.app.get(new_reminder_route).status_code == STATUS_REDIRECT
                assert self.app.post(new_reminder_route).status_code == STATUS_REDIRECT
                new_top_route = "/type/tops/new/{}".format(protocoltype.id)
                assert self.app.get(new_top_route).status_code == STATUS_REDIRECT
                assert self.app.post(new_top_route).status_code == STATUS_REDIRECT
                new_meta_route = "/defaultmeta/new/{}".format(protocoltype.id)
                assert self.app.get(new_meta_route).status_code == STATUS_REDIRECT
                assert self.app.post(new_meta_route).status_code == STATUS_REDIRECT

    def test_protocols(self):
        with proto3.app.app_context():
            new_route = "/protocol/new"
            assert self.app.get(new_route).status_code == STATUS_REDIRECT
            assert self.app.post(new_route).status_code == STATUS_REDIRECT
            protocols = Protocol.query.all()
            for protocol in protocols:
                visible = protocol.protocoltype.has_public_view_right(None, check_networks=False)
                state_ok_or_redirect = STATUS_OK if visible else STATUS_REDIRECT
                show_route = "/protocol/show/{}".format(protocol.id)
                assert self.app.get(show_route).status_code == state_ok_or_redirect
                assert self.app.post(show_route).status_code == STATUS_METHOD
                
                

if __name__ == "__main__":
    unittest.main()
