
class DateNotMatchingException(Exception):
    def __init__(self, original_date, protocol_date):
        self.original_date = original_date
        self.protocol_date = protocol_date
