# change this file to add additional keywords
def make_states(TodoState):
    # do not remove any of these
    # any of these mappings must be in NAME_TO_STATE as well
    STATE_TO_NAME = {
        TodoState.open: "offen",
        TodoState.waiting: "wartet auf Rückmeldung",
        TodoState.in_progress: "in Bearbeitung",
        TodoState.after: "ab",
        TodoState.before: "vor",
        TodoState.orphan: "verwaist",
        TodoState.done: "erledigt",
        TodoState.rejected: "abgewiesen",
        TodoState.obsolete: "obsolet"
    }

    # the text version has to be in lower case
    # Please don't add something that matches a date
    NAME_TO_STATE = {
        "offen": TodoState.open,
        "open": TodoState.open,
        "wartet auf rückmeldung": TodoState.waiting,
        "wartet": TodoState.waiting,
        "waiting": TodoState.waiting,
        "in bearbeitung": TodoState.in_progress,
        "bearbeitung": TodoState.in_progress,
        "läuft": TodoState.in_progress,
        "in progress": TodoState.in_progress,
        "ab": TodoState.after,
        "erst ab": TodoState.after,
        "nicht vor": TodoState.after,
        "wiedervorlage": TodoState.after,
        "after": TodoState.after,
        "not before": TodoState.after,
        "vor": TodoState.before,
        "bis": TodoState.before,
        "nur vor": TodoState.before,
        "nicht nach": TodoState.before,
        "before": TodoState.before,
        "not after": TodoState.before,
        "verwaist": TodoState.orphan,
        "orphan": TodoState.orphan,
        "orphaned": TodoState.orphan,
        "erledigt": TodoState.done,
        "fertig": TodoState.done,
        "done": TodoState.done,
        "abgewiesen": TodoState.rejected,
        "abgelehnt": TodoState.rejected,
        "passiert nicht": TodoState.rejected,
        "nie": TodoState.rejected,
        "niemals": TodoState.rejected,
        "rejected": TodoState.rejected,
        "obsolet": TodoState.obsolete,
        "veraltet": TodoState.obsolete,
        "zu spät": TodoState.obsolete,
        "obsolete": TodoState.obsolete
    }
    return STATE_TO_NAME, NAME_TO_STATE
