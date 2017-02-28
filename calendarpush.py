from datetime import datetime, timedelta
import random
import quopri

from caldav import DAVClient, Principal, Calendar, Event
from vobject.base import ContentLine

import config

class CalendarException(Exception):
    pass

class Client:
    def __init__(self, calendar=None, url=None):
        self.url = url if url is not None else config.CALENDAR_URL
        self.client = DAVClient(self.url)
        self.principal = self.client.principal()
        if calendar is not None:
            self.calendar = self.get_calendar(calendar)
        else:
            self.calendar = calendar

    def get_calendars(self):
        return [
            calendar.name
            for calendar in self.principal.calendars()
        ]

    def get_calendar(self, calendar_name):
        candidates = self.principal.calendars()
        for calendar in candidates:
            if calendar.name == calendar_name:
                return calendar
        raise CalendarException("No calendar named {}.".format(calendar_name))

    def set_event_at(self, begin, name, description):
        candidates = [
            Event.from_raw_event(raw_event)
            for raw_event in self.calendar.date_search(begin)
        ]
        candidates = [event for event in candidates if event.name == name]
        event = None
        if len(candidates) == 0:
            event = Event(None, name, description, begin,
                begin + timedelta(hours=config.CALENDAR_DEFAULT_DURATION))
            vevent = self.calendar.add_event(event.to_vcal())
            event.vevent = vevent
        else:
            event = candidates[0]
        event.set_description(description)
        event.vevent.save()


NAME_KEY = "summary"
DESCRIPTION_KEY = "description"
BEGIN_KEY = "dtstart"
END_KEY = "dtend"
def _get_item(content, key):
    if key in content:
        return content[key][0].value
    return None
        
class Event:
    def __init__(self, vevent, name, description, begin, end):
        self.vevent = vevent
        self.name = name
        self.description = description
        self.begin = begin
        self.end = end

    @staticmethod
    def from_raw_event(vevent):
        raw_event = vevent.instance.contents["vevent"][0]
        content = raw_event.contents
        name = _get_item(content, NAME_KEY)
        description = _get_item(content, DESCRIPTION_KEY)
        begin = _get_item(content, BEGIN_KEY)
        end = _get_item(content, END_KEY)
        return Event(vevent=vevent, name=name, description=description,
            begin=begin, end=end)

    def set_description(self, description):
        raw_event = self.vevent.instance.contents["vevent"][0]
        self.description = description
        encoded = encode_quopri(description)
        if DESCRIPTION_KEY not in raw_event.contents:
            raw_event.contents[DESCRIPTION_KEY] = [ContentLine(DESCRIPTION_KEY, {"ENCODING": ["QUOTED-PRINTABLE"]}, encoded)]
        else:
            content_line = raw_event.contents[DESCRIPTION_KEY][0]
            content_line.value = encoded
            content_line.params["ENCODING"] = ["QUOTED-PRINTABLE"]

    def __repr__(self):
        return "<Event(name='{}', description='{}', begin={}, end={})>".format(
            self.name, self.description, self.begin, self.end)

    def to_vcal(self):
        offset = get_timezone_offset()
        return """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//FSMPI Protokollsystem//CalDAV Client//EN
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now}
DTSTART:{begin}
DTEND:{end}
SUMMARY:{summary}
DESCRIPTION;ENCODING=QUOTED-PRINTABLE:{description}
END:VEVENT
END:VCALENDAR""".format(
            uid=create_uid(), now=date_format(datetime.now()-offset),
            begin=date_format(self.begin-offset), end=date_format(self.end-offset),
            summary=self.name,
            description=encode_quopri(self.description))

def create_uid():
    return str(random.randint(0, 1e10)).rjust(10, "0")

def date_format(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")

def get_timezone_offset():
    difference = datetime.now() - datetime.utcnow()
    return timedelta(hours=round(difference.seconds / 3600 + difference.days * 24))

def encode_quopri(text):
    return quopri.encodestring(text.encode("utf-8")).replace(b"\n", b"=0D=0A").decode("utf-8")

def main():
    client = Client("Protokolltest")
    client.set_event_at(datetime(2017, 2, 27, 19, 0), "FSS", "Tagesordnung\nTOP 1")

if __name__ == "__main__":
    if config.CALENDAR_ACTIVE:
        main()
