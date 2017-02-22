import regex as re
import sys
from collections import OrderedDict

class ParserException(Exception):
    name = "Parser Exception"
    has_explanation = False
    #explanation = "The source did generally not match the expected protocol syntax."
    def __init__(self, message, linenumber=None):
        self.message = message
        self.linenumber = linenumber

    def __str__(self):
        result = ""
        if self.linenumber is not None:
            result = "Exception at line {}: {}".format(self.linenumber, self.message)
        else:
            result = "Exception: {}".format(self.message)
        if self.has_explanation:
            result += "\n" + self.explanation
        return result

class Element:
    """
    Generic (abstract) base element. Should never really exist.
    Template for what an element class should contain.
    """
    def render(self):
        """
        Renders the element to TeX.
        Returns:
        - a TeX-representation of the element
        """
        return "Generic Base Syntax Element, this is not supposed to appear."

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}element".format(" " * level))

    @staticmethod
    def parse(match, current, linenumber=None):
        """
        Parses a match of this elements pattern.
        Arguments:
        - match: the match of this elements pattern
        - current: the current element of the document. Should be a fork. May be modified.
        - linenumber: the current line number, for error messages
        Returns:
        - the new current element
        - the line number after parsing this element
        """
        raise ParserException("Trying to parse the generic base element!", linenumber)

    @staticmethod
    def parse_inner(match, current, linenumber=None):
        """
        Do the parsing for every element. Checks if the match exists.
        Arguments:
        - match: the match of this elements pattern
        - current = the current element of the document. Should be a fork.
        - linenumber: the current line number, for error messages
        Returns:
        - new line number
        """
        if match is None:
            raise ParserException("Source does not match!", linenumber)
        length = match.group().count("\n")
        return length + (0 if linenumber is None else linenumber)

    @staticmethod
    def parse_outer(element, current):
        """
        Handle the insertion of the object into the tree.
        Arguments:
        - element: the new parsed element to insert
        - current: the current element of the parsed document
        Returns:
        - the new current element
        """
        current.append(element)
        if isinstance(element, Fork):
            return element
        return current

    PATTERN = r"x(?<!x)" # yes, a master piece, but it should never be called

class Content(Element):
    def __init__(self, children, linenumber):
        self.children = children
        self.linenumber = linenumber

    def render(self):
        return "".join(map(lambda e: e.render(), self.children))

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}content:".format(" " * level))
        for child in self.children:
            child.dump(level + 1)

    def get_tags(self, tags):
        tags.extend([child for child in self.children if isinstance(child, Tag)])
        return tags

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        if match.group("content") is None:
            raise ParserException("Content is missing its content!", linenumber)
        content = match.group("content")
        element = Content.from_content(content, linenumber)
        if len(content) == 0:
            return current, linenumber
        current = Element.parse_outer(element, current)
        return current, linenumber

    @staticmethod
    def from_content(content, linenumber):
        children = []
        while len(content) > 0:
            matched = False
            for pattern in TEXT_PATTERNS:
                match = pattern.match(content)
                if match is not None:
                    matched = True
                    children.append(TEXT_PATTERNS[pattern](match, linenumber))
                    content = content[len(match.group()):]
                    break
            if not matched:
                raise ParserException("Content does not match inner!", linenumber)
        return Content(children, linenumber)

    # v1: has problems with missing semicolons
    #PATTERN = r"\s*(?<content>(?:[^\[\];]+)?(?:\[[^\]]+\][^;\[\]]*)*);"
    # v2: does not require the semicolon, but the newline
    PATTERN = r"\s*(?<content>(?:[^\[\];\r\n]+)?(?:\[[^\]\r\n]+\][^;\[\]\r\n]*)*);?"

class Text:
    def __init__(self, text, linenumber):
        self.text = text
        self.linenumber = linenumber

    def render(self):
        return self.text

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}text: {}".format(" " * level, self.text))

    @staticmethod
    def parse(match, linenumber):
        if match is None:
            raise ParserException("Text is not actually a text!", linenumber)
        content = match.group("text")
        if content is None:
            raise ParserException("Text is empty!", linenumber)
        return Text(content, linenumber)

    PATTERN = r"(?<text>[^\[]+)(?:(?=\[)|$)"


class Tag:
    def __init__(self, name, values, linenumber):
        self.name = name
        self.values = values
        self.linenumber = linenumber

    def render(self):
        return r"\textbf{{{}:}} {}".format(self.name, "; ".join(self.values));

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}tag: {}: {}".format(" " * level, self.name, "; ".join(self.values)))

    @staticmethod
    def parse(match, linenumber):
        if match is None:
            raise ParserException("Tag is not actually a tag!", linenumber)
        content = match.group("content")
        if content is None:
            raise ParserException("Tag is empty!", linenumber)
        parts = content.split(";")
        return Tag(parts[0], parts[1:], linenumber)

    PATTERN = r"\[(?<content>(?:[^;\]]*;)*(?:[^;\]]*))\]"

class Empty(Element):
    def __init__(self, linenumber):
        linenumber = linenumber

    def render(self):
        return ""

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}empty".format(" " * level))

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        return current, linenumber

    PATTERN = r"\s+"

class Remark(Element):
    def __init__(self, name, value, linenumber):
        self.name = name
        self.value = value
        self.linenumber = linenumber

    def render(self):
        return r"\textbf{{{}}}: {}".format(self.name, self.value)

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}remark: {}: {}".format(" " * level, self.name, self.value))

    def get_tags(self, tags):
        return tags

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        if match.group("content") is None:
            raise ParserException("Remark is missing its content!", linenumber)
        content = match.group("content")
        parts = content.split(";", 1)
        if len(parts) < 2:
            raise ParserException("Remark value is empty!", linenumber)
        name, value = parts
        element = Remark(name, value, linenumber)
        current = Element.parse_outer(element, current)
        return current, linenumber

    PATTERN = r"\s*\#(?<content>[^\n]+)"

class Fork(Element):
    def __init__(self, environment, name, parent, linenumber, children=None):
        self.environment = environment if environment is None or len(environment) > 0 else None
        self.name = name.strip() if (name is not None and len(name) > 0) else None
        self.parent = parent
        self.linenumber = linenumber
        self.children = [] if children is None else children

    def dump(self, level=None):
        if level is None:
            level = 0
        print("{}fork: {}".format(" " * level, self.name))
        for child in self.children:
            child.dump(level + 1)

    def render(self):
        return ((self.name if self.name is not None and len(self.name) > 0 else "")
            + r"\begin{itemize}" + "\n"
            + "\n".join(map(lambda e: r"\item {}".format(e.render()), self.children)) + "\n"
            + r"\end{itemize}" + "\n")

    def get_tags(self, tags=None):
        if tags is None:
            tags = []
        for child in self.children:
            child.get_tags(tags)
        return tags

    def is_anonymous(self):
        return self.environment == None

    def is_root(self):
        return self.parent is None

    @staticmethod
    def create_root():
        return Fork(None, None, None, 0)

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        environment = match.group("environment")
        name1 = match.group("name1")
        name2 = match.group("name2")
        name = ""
        if name1 is not None:
            name = name1
        if name2 is not None:
            name += " {}".format(name2)
        element = Fork(environment, name, current, linenumber)
        current = Element.parse_outer(element, current)
        return current, linenumber

    @staticmethod
    def parse_end(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        if current.is_root():
            raise ParserException("Found end tag for root element!", linenumber)
        current = current.parent
        return current, linenumber

    def append(self, element):
        self.children.append(element)

    PATTERN = r"\s*(?<name1>[^{};]+)?{(?<environment>\S+)?\h*(?<name2>[^\n]+)?"
    END_PATTERN = r"\s*};?"

PATTERNS = OrderedDict([
    (re.compile(Fork.PATTERN), Fork.parse),
    (re.compile(Fork.END_PATTERN), Fork.parse_end),
    (re.compile(Remark.PATTERN), Remark.parse),
    (re.compile(Content.PATTERN), Content.parse),
    (re.compile(Empty.PATTERN), Empty.parse)
])

TEXT_PATTERNS = OrderedDict([
    (re.compile(Text.PATTERN), Text.parse),
    (re.compile(Tag.PATTERN), Tag.parse)
])

def parse(source):
    linenumber = 1
    tree = Fork.create_root()
    current = tree
    while len(source) > 0:
        found = False
        for pattern in PATTERNS:
            match = pattern.match(source)
            if match is not None:
                source = source[len(match.group()):]
                current, linenumber = PATTERNS[pattern](match, current, linenumber)
                found = True
                break
        if not found:
            raise ParserException("No matching syntax element found!", linenumber)
    if current is not tree:
        raise ParserException("Source ended within fork! (started at line {})".format(current.linenumber))
    return tree

def main(test_file_name=None):
    source = ""
    test_file_name = test_file_name or "source0"
    with open("test/{}.txt".format(test_file_name)) as f:
        source = f.read()
    try:
        tree = parse(source)
        tree.dump()
    except ParserException as e:
        print(e)
    else:
        print("worked!")
    

if __name__ == "__main__":
    test_file_name = sys.argv[1] if len(sys.argv) > 1 else None
    exit(main(test_file_name))
