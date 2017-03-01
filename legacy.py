from datetime import datetime
from fuzzywuzzy import fuzz, process
import tempfile

from models.database import Todo, OldTodo, Protocol, ProtocolType
from shared import db

import config

def log_fuzzy(text):
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmpfile:
        tmpfile.write(text + "\n\n")
    print(text)

def lookup_todo_id(old_candidates, new_who, new_description):
    # Check for perfect matches
    for candidate in old_candidates:
        if candidate.who == new_who and candidate.description == new_description:
            return candidate.old_id
    # Accept if who has been changed
    for candidate in old_candidates:
        if candidate.description == new_description:
            return candidate.old_id
    # Do fuzzy matching on description
    content_to_number = {
        candidate.description: candidate.old_id
        for candidate in old_candidates
    }
    best_match, best_match_score = process.extractOne(
        new_description, content_to_number.keys())
    if best_match_score >= config.FUZZY_MIN_SCORE:
        log_fuzzy("Used fuzzy matching on '{}', got '{}' with score {}.".format(
            new_description, best_match, best_match_score))
        return content_to_number[best_match]
    else:
        log_fuzzy("Best match for '{}' is '{}' with score {}, rejecting.".format(
            new_description, best_match, best_match_score))
        return None

INSERT_PROTOCOLTYPE = "INSERT INTO `protocolManager_protocoltype`"
INSERT_PROTOCOL = "INSERT INTO `protocolManager_protocol`"
INSERT_TODO = "INSERT INTO `protocolManager_todo`"

def import_old_protocols(sql_text):
    protocoltype_lines = []
    protocol_lines = []
    for line in sql_text.splitlines():
        if line.startswith(INSERT_PROTOCOLTYPE):
            protocoltype_lines.append(line)
        elif line.startswith(INSERT_PROTOCOL):
            protocol_lines.append(line)
    if (len(protocoltype_lines) == 0
    or len(protocol_lines) == 0):
        raise ValueError("Necessary lines not found.")
    type_id_to_handle = {}
    for type_line in protocoltype_lines:
        for id, handle, name, mail, protocol_id in _split_insert_line(type_line):
            type_id_to_handle[int(id)] = handle.lower()
    protocols = []
    for protocol_line in protocol_lines:
        for (protocol_id, old_type_id, date, source, textsummary, htmlsummary,
            deleted, sent, document_id) in _split_insert_line(protocol_line):
            date = datetime.strptime(date, "%Y-%m-%d")
            handle = type_id_to_handle[int(old_type_id)]
            type = ProtocolType.query.filter(ProtocolType.short_name.ilike(handle)).first()
            if type is None:
                raise KeyError("No protocoltype for handle '{}'.".format(handle))
            protocol = Protocol(type.id, date, source=source)
            db.session.add(protocol)
            db.session.commit()
            import tasks
            protocols.append(protocol)
    for protocol in sorted(protocols, key=lambda p: p.date):
        print(protocol.date)
        tasks.parse_protocol(protocol)


def import_old_todos(sql_text):
    protocoltype_lines = []
    protocol_lines = []
    todo_lines = []
    for line in sql_text.splitlines():
        if line.startswith(INSERT_PROTOCOLTYPE):
            protocoltype_lines.append(line)
        elif line.startswith(INSERT_PROTOCOL):
            protocol_lines.append(line)
        elif line.startswith(INSERT_TODO):
            todo_lines.append(line)
    if (len(protocoltype_lines) == 0
    or len(protocol_lines) == 0
    or len(todo_lines) == 0):
        raise ValueError("Necessary lines not found.")
    type_id_to_handle = {}
    for type_line in protocoltype_lines:
        for id, handle, name, mail, protocol_id in _split_insert_line(type_line):
            type_id_to_handle[int(id)] = handle.lower()
    protocol_id_to_key = {}
    for protocol_line in protocol_lines:
        for (protocol_id, type_id, date, source, textsummary, htmlsummary,
            deleted, sent, document_id) in _split_insert_line(protocol_line):
            handle = type_id_to_handle[int(type_id)]
            date_string = date [2:]
            protocol_id_to_key[int(protocol_id)] = "{}-{}".format(handle, date_string)
    todos = []
    for todo_line in todo_lines:
        for old_id, protocol_id, who, what, start_time, end_time, done in _split_insert_line(todo_line):
            protocol_id = int(protocol_id)
            if protocol_id not in protocol_id_to_key:
                print("Missing protocol with ID {} for Todo {}".format(protocol_id, what))
                continue
            todo = OldTodo(old_id=old_id, who=who, description=what,
                protocol_key=protocol_id_to_key[protocol_id])
            todos.append(todo)
    OldTodo.query.delete()
    db.session.commit()
    for todo in todos:
        db.session.add(todo)
    db.session.commit()
        
def _split_insert_line(line):
    insert_part, values_part = line.split("VALUES", 1)
    return _split_base_level(values_part)

def _split_base_level(text, begin="(", end=")", separator=",", string_terminator="'", line_end=";", ignore=" ", escape="\\"):
    raw_parts = []
    current_part = None
    index = 0
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            current_part += char
            escaped = False
        elif current_part is None:
            if char == ignore:
                continue
            elif char == begin:
                current_part = ""
            elif char == line_end:
                break
            elif char == separator:
                pass
            else:
                raise ValueError(
                    "Found invalid char '{}' at position {}".format(
                        char, index))
        else:
            if in_string:
                current_part += char
                if char == escape:
                    escaped = True
                elif char == string_terminator:
                    in_string = False
            else:
                if char == string_terminator:
                    current_part += char
                    in_string = True
                elif char == end:
                    raw_parts.append(current_part)
                    current_part = None
                else:
                    current_part += char
        index += 1
    parts = []
    for part in raw_parts:
        fields = []
        current_field = ""
        in_string = False
        escaped = False
        for char in part:
            if escaped:
                if char == "n":
                    current_field += "\n"
                elif char == "r":
                    current_field += "\r"
                elif char == "t":
                    current_field += "\t"
                else:
                    if char not in "\"'\\":
                        print("escaped char: '{}'".format(char))
                    current_field += char
                escaped = False
            elif in_string:
                if char == escape:
                    escaped = True
                elif char == string_terminator:
                    in_string = False
                else:
                    current_field += char
            else:
                if char == string_terminator:
                    in_string = True
                elif char == separator:
                    fields.append(current_field)
                    current_field = ""
                else:
                    current_field += char
        if len(current_field) > 0:
            fields.append(current_field)
        parts.append(fields)
    return parts
        
    
