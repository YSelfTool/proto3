import regex as re
import sys
from collections import OrderedDict
from enum import Enum

from shared import escape_tex
from utils import footnote_hash

from shared import config

INDENT_LETTER = "-"


class ParserException(Exception):
    name = "Parser Exception"
    has_explanation = False

    def __init__(self, message, linenumber=None, tree=None):
        self.message = message
        self.linenumber = linenumber
        self.tree = tree

    def __str__(self):
        result = ""
        if self.linenumber is not None:
            result = "Exception at line {}: {}".format(
                self.linenumber, self.message)
        else:
            result = "Exception: {}".format(self.message)
        if self.has_explanation:
            result += "\n" + self.explanation
        return result


class RenderType(Enum):
    latex = 0
    wikitext = 1
    plaintext = 2
    html = 3
    dokuwiki = 4


def _not_implemented(self, render_type):
    return NotImplementedError(
        "The rendertype {} has not been implemented for {}.".format(
            render_type.name, self.__class__.__name__))


class Element:
    """
    Generic (abstract) base element. Should never really exist.
    Template for what an element class should contain.
    """
    def render(self, render_type, show_private, level=None, protocol=None):
        """
        Renders the element to TeX.
        Returns:
        - a TeX-representation of the element
        """
        return "Generic Base Syntax Element, this is not supposed to appear."

    def dump(self, level=None):
        if level is None:
            level = 0
        return "{}element".format(INDENT_LETTER * level)

    @staticmethod
    def parse(match, current, linenumber=None):
        """
        Parses a match of this elements pattern.
        Arguments:
        - match: the match of this elements pattern
        - current: the current element of the document. Should be a fork.
            May be modified.
        - linenumber: the current line number, for error messages
        Returns:
        - the new current element
        - the line number after parsing this element
        """
        raise ParserException(
            "Trying to parse the generic base element!", linenumber)

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
        else:
            element.fork = current
            return current

    PATTERN = r"x(?<!x)"


class Content(Element):
    def __init__(self, children, linenumber):
        self.children = children
        self.linenumber = linenumber

    def render(self, render_type, show_private, level=None, protocol=None):
        return "".join(map(lambda e: e.render(
            render_type, show_private, level=level, protocol=protocol),
            self.children))

    def dump(self, level=None):
        if level is None:
            level = 0
        result_lines = ["{}content:".format(INDENT_LETTER * level)]
        for child in self.children:
            result_lines.append(child.dump(level + 1))
        return "\n".join(result_lines)

    def get_tags(self, tags):
        tags.extend([
            child for child in self.children
            if isinstance(child, Tag)
        ])
        return tags

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        if match.group("content") is None:
            raise ParserException(
                "Content is missing its content!", linenumber)
        content = match.group("content")
        element = Content.from_content(content, current, linenumber)
        if len(content) == 0:
            return current, linenumber
        current = Element.parse_outer(element, current)
        return current, linenumber

    @staticmethod
    def from_content(content, current, linenumber):
        children = []
        while len(content) > 0:
            matched = False
            for pattern in TEXT_PATTERNS:
                match = pattern.match(content)
                if match is not None:
                    matched = True
                    children.append(TEXT_PATTERNS[pattern](
                        match, current, linenumber))
                    content = content[len(match.group()):]
                    break
            if not matched:
                raise ParserException(
                    "Dies ist kein valider Tag! "
                    "(mögliche Tags sind: {})".format(
                        ", ".join(Tag.KNOWN_TAGS)),
                    linenumber)
        return Content(children, linenumber)

    PATTERN = (
        r"\s*(?<content>(?:(?:[^\[\];\r\n{}]+)|(?:[^\[\];\r\n{}]+)?"
        r"(?:\[[^\]\r\n{}]+\][^;\[\]\r\n{}]*)+)+);?")


class Text:
    def __init__(self, text, linenumber, fork):
        self.text = text
        self.linenumber = linenumber
        self.fork = fork

    def render(self, render_type, show_private, level=None, protocol=None):
        if render_type == RenderType.latex:
            return escape_tex(self.text)
        elif render_type == RenderType.wikitext:
            return self.text
        elif render_type == RenderType.plaintext:
            return self.text
        elif render_type == RenderType.html:
            return self.text
        elif render_type == RenderType.dokuwiki:
            return self.text
        else:
            raise _not_implemented(self, render_type)

    def dump(self, level=None):
        if level is None:
            level = 0
        return "{}text: {}".format(INDENT_LETTER * level, self.text)

    @staticmethod
    def parse(match, current, linenumber):
        if match is None:
            raise ParserException("Text is not actually a text!", linenumber)
        content = match.group("text")
        if content is None:
            raise ParserException("Text is empty!", linenumber)
        return Text(content, linenumber, current)

    PATTERN = r"(?<text>\[?[^\[{}]+)(?:(?=\[)|$)"


class Tag:
    def __init__(self, name, values, linenumber, fork):
        self.name = name
        self.values = values
        self.linenumber = linenumber
        self.fork = fork

    def render(self, render_type, show_private, level=None, protocol=None):
        if render_type == RenderType.latex:
            if self.name == "url":
                return r"\url{{{}}}".format(self.values[0])
            elif self.name == "todo":
                if not show_private:
                    return ""
                return self.todo.render_latex(current_protocol=protocol)
            elif self.name == "beschluss":
                if len(self.decision.categories):
                    return r"\Beschluss[{}]{{{}}}".format(
                        escape_tex(self.decision.get_categories_str()),
                        escape_tex(self.decision.content))
                else:
                    return r"\Beschluss{{{}}}".format(self.decision.content)
            elif self.name == "footnote":
                return r"\footnote{{{}}}".format(self.values[0])
            return r"\textbf{{{}:}} {}".format(
                escape_tex(self.name.capitalize()),
                escape_tex(";".join(self.values)))
        elif render_type == RenderType.plaintext:
            if self.name == "url":
                return self.values[0]
            elif self.name == "todo":
                if not show_private:
                    return ""
                return self.values[0]
            elif self.name == "footnote":
                return "[^]({})".format(self.values[0])
            return "{}: {}".format(
                self.name.capitalize(), ";".join(self.values))
        elif render_type == RenderType.wikitext:
            if self.name == "url":
                return "[{0} {0}]".format(self.values[0])
            elif self.name == "todo":
                if not show_private:
                    return ""
                return self.todo.render_wikitext(current_protocol=protocol)
            elif self.name == "footnote":
                return "<ref>{}</ref>".format(self.values[0])
            return "'''{}:''' {}".format(
                self.name.capitalize(), ";".join(self.values))
        elif render_type == RenderType.html:
            if self.name == "url":
                return "<a href=\"{0}\">{0}</a>".format(self.values[0])
            elif self.name == "todo":
                if not show_private:
                    return ""
                if getattr(self, "todo", None) is not None:
                    return self.todo.render_html(current_protocol=protocol)
                else:
                    return "<b>Todo:</b> {}".format(";".join(self.values))
            elif self.name == "beschluss":
                if getattr(self, "decision", None) is not None:
                    parts = ["<b>Beschluss:</b>", self.decision.content]
                    if len(self.decision.categories) > 0:
                        parts.append("<i>{}</i>".format(
                            self.decision.get_categories_str()))
                    return " ".join(parts)
                else:
                    return "<b>Beschluss:</b> {}".format(self.values[0])
            elif self.name == "footnote":
                return (
                    '<sup id="#fnref{0}"><a href="#fn{0}">Fn</a></sup>'.format(
                        footnote_hash(self.values[0])))
            return "[{}: {}]".format(self.name, ";".join(self.values))
        elif render_type == RenderType.dokuwiki:
            if self.name == "url":
                return self.values[0]
            elif self.name == "todo":
                if not show_private:
                    return ""
                return self.todo.render_wikitext(
                    current_protocol=protocol, use_dokuwiki=True)
            elif self.name == "beschluss":
                return "**{}:** {}".format(
                    self.name.capitalize(), ";".join(self.values))
            elif self.name == "footnote":
                return "(({}))".format(self.values[0])
            else:
                return "**{}:** {}".format(
                    self.name.capitalize(), ";".join(self.values))
        else:
            raise _not_implemented(self, render_type)

    def dump(self, level=None):
        if level is None:
            level = 0
        return "{}tag: {}: {}".format(
            INDENT_LETTER * level, self.name, "; ".join(self.values))

    @staticmethod
    def parse(match, current, linenumber):
        if match is None:
            raise ParserException("Tag is not actually a tag!", linenumber)
        content = match.group("content")
        if content is None:
            raise ParserException("Tag is empty!", linenumber)
        parts = content.split(";")
        return Tag(parts[0], parts[1:], linenumber, current)

    PATTERN = r"\[(?<content>[^\]]*)\]"

    KNOWN_TAGS = ["todo", "url", "beschluss", "footnote", "sitzung"]


class Empty(Element):
    def __init__(self, linenumber):
        linenumber = linenumber

    def render(self, render_type, show_private, level=None, protocol=None):
        return ""

    def dump(self, level=None):
        if level is None:
            level = 0
        return "{}empty".format(INDENT_LETTER * level)

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        return current, linenumber

    PATTERN = r"(?:\s+|;)"


class Remark(Element):
    def __init__(self, name, value, linenumber):
        self.name = name
        self.value = value
        self.linenumber = linenumber

    def render(self, render_type, show_private, level=None, protocol=None):
        if render_type == RenderType.latex:
            return r"\textbf{{{}}}: {}".format(self.name, self.value)
        elif render_type == RenderType.wikitext:
            return "{}: {}".format(self.name, self.value)
        elif render_type == RenderType.plaintext:
            return "{}: {}".format(RenderType.plaintex)
        elif render_type == RenderType.html:
            return "<p>{}: {}</p>".format(self.name, self.value)
        elif render_type == RenderType.dokuwiki:
            return r"{}: {}\\".format(self.name, self.value)
        else:
            raise _not_implemented(self, render_type)

    def dump(self, level=None):
        if level is None:
            level = 0
        return "{}remark: {}: {}".format(
            INDENT_LETTER * level, self.name, self.value)

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
    def __init__(self, is_top, name, parent, linenumber, children=None, is_extra=False):
        self.is_top = is_top
        self.is_extra = is_extra
        self.name = name.strip() if name else None
        self.parent = parent
        self.linenumber = linenumber
        self.children = [] if children is None else children

    def dump(self, level=None):
        if level is None:
            level = 0
        result_lines = [
            "{}fork: {}'{}'".format(
                INDENT_LETTER * level,
                "TOP " if self.is_top else "",
                self.name)
        ]
        for child in self.children:
            result_lines.append(child.dump(level + 1))
        return "\n".join(result_lines)

    def test_private(self, name):
        if name is None:
            return False
        stripped_name = name.replace(":", "").strip()
        return stripped_name in config.PRIVATE_KEYWORDS

    def render(self, render_type, show_private, level, protocol=None):
        name_line = self.name if self.name is not None else ""
        if level == 0 and self.name == "Todos" and not show_private:
            return ""
        if render_type == RenderType.latex:
            if self.is_extra:
                return r"\textit{[Dieser Tagesordnungspunkt wird in einem eigenem PDF exportiert.]}"

            begin_line = r"\begin{itemize}"
            end_line = r"\end{itemize}"
            content_parts = []
            for child in self.children:
                part = child.render(
                    render_type, show_private, level=level + 1,
                    protocol=protocol)
                if len(part.strip()) == 0:
                    continue
                if not part.startswith(r"\item"):
                    part = r"\item {}".format(part)
                content_parts.append(part)
            content_lines = "\n".join(content_parts)
            if len(content_lines.strip()) == 0:
                content_lines = "\\item Nichts\n"
            if level == 0:
                return "\n".join([begin_line, content_lines, end_line])
            elif self.test_private(self.name):
                if show_private:
                    return (r"\begin{tcolorbox}[breakable,title=Interner "
                            r"Abschnitt]" + "\n"
                            + r"\begin{itemize}" + "\n"
                            + content_lines + "\n"
                            + r"\end{itemize}" + "\n"
                            + r"\end{tcolorbox}")
                else:
                    return (r"\textit{[An dieser Stelle wurde intern "
                            r"protokolliert.]}")
            else:
                return "\n".join([
                    escape_tex(name_line), begin_line,
                    content_lines, end_line
                ])
        elif (render_type == RenderType.wikitext
                or render_type == RenderType.dokuwiki):
            equal_signs = level + 2
            if render_type == RenderType.dokuwiki:
                equal_signs = 5 - level
            title_line = "{0} {1} {0}".format("=" * equal_signs, name_line)
            content_parts = []
            for child in self.children:
                part = child.render(
                    render_type, show_private, level=level + 1,
                    protocol=protocol)
                if len(part.strip()) == 0:
                    continue
                content_parts.append(part)
            content_lines = "{}\n\n{}\n".format(
                title_line, "\n\n".join(content_parts))
            if self.test_private(self.name) and not show_private:
                return ""
            else:
                return content_lines
        elif render_type == RenderType.plaintext:
            title_line = "{} {}".format("#" * (level + 1), name_line)
            content_parts = []
            for child in self.children:
                part = child.render(
                    render_type, show_private, level=level + 1,
                    protocol=protocol)
                if len(part.strip()) == 0:
                    continue
                content_parts.append(part)
            content_lines = "{}\n{}".format(
                title_line, "\n".join(content_parts))
            if self.test_private(self.name) and not show_private:
                return ""
            else:
                return content_lines
        elif render_type == RenderType.html:
            depth = level + 1 + getattr(config, "HTML_LEVEL_OFFSET", 0)
            content_lines = ""
            if depth < 5:
                title_line = "<h{depth}>{content}</h{depth}>".format(
                    depth=depth, content=name_line)
                content_parts = []
                for child in self.children:
                    part = child.render(
                        render_type, show_private, level=level + 1,
                        protocol=protocol)
                    if len(part.strip()) == 0:
                        continue
                    content_parts.append("<p>{}</p>".format(part))
                content_lines = "{}\n\n{}".format(
                    title_line, "\n".join(content_parts))
            else:
                content_parts = []
                for child in self.children:
                    part = child.render(
                        render_type, show_private, level=level + 1,
                        protocol=protocol)
                    if len(part.strip()) == 0:
                        continue
                    content_parts.append("<li>{}</li>".format(part))
                content_lines = "{}\n<ul>\n{}\n</ul>".format(
                    name_line, "\n".join(content_parts))
            if self.test_private(self.name) and not show_private:
                return ""
            else:
                return content_lines
        else:
            raise _not_implemented(self, render_type)

    def get_tags(self, tags=None):
        if tags is None:
            tags = []
        for child in self.children:
            child.get_tags(tags)
        return tags

    def is_anonymous(self):
        return self.name is None

    def is_root(self):
        return self.parent is None

    def get_top(self):
        if self.is_root() or self.parent.is_root():
            return self
        return self.parent.get_top()

    def get_top_number(self):
        if self.is_root():
            return 1
        top = self.get_top()
        tops = [
            child
            for child in top.parent.children
            if isinstance(child, Fork)
        ]
        return tops.index(top) + 1

    def get_maxdepth(self):
        child_depths = [
            child.get_maxdepth()
            for child in self.children
            if isinstance(child, Fork)
        ]
        if len(child_depths) > 0:
            return max(child_depths) + 1
        else:
            return 1

    def get_visible_elements(self, show_private, elements=None):
        if elements is None:
            elements = set()
        if show_private or not self.test_private(self.name):
            for child in self.children:
                elements.add(child)
                if isinstance(child, Content):
                    elements.update(child.children)
                elif isinstance(child, Fork):
                    child.get_visible_elements(show_private, elements)
        return elements

    @staticmethod
    def create_root():
        return Fork(None, None, None, 0)

    @staticmethod
    def parse(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        topname = match.group("topname")
        name = match.group("name")
        extra = match.group("extra")

        is_top = False
        is_extra = False
        if topname is not None:
            is_top = True
            name = topname
            if extra is not None:
                is_extra = True

        element = Fork(is_top, name, current, linenumber, is_extra=is_extra)
        current = Element.parse_outer(element, current)
        return current, linenumber

    @staticmethod
    def parse_end(match, current, linenumber=None):
        linenumber = Element.parse_inner(match, current, linenumber)
        if current.is_root():
            raise ParserException(
                "Found end tag for root element!", linenumber)
        current = current.parent
        return current, linenumber

    def append(self, element):
        self.children.append(element)

    PATTERN = (
        r"\s*(?<name>(?:[^{};\n])+)?\n?\s*{(?:(?<extra>!)?TOP\h*(?<topname>[^;{}\n]+))?")
    END_PATTERN = r"\s*};?"


PATTERNS = OrderedDict([
    (re.compile(Fork.PATTERN), Fork.parse),
    (re.compile(Fork.END_PATTERN), Fork.parse_end),
    (re.compile(Remark.PATTERN), Remark.parse),
    (re.compile(Content.PATTERN), Content.parse),
    (re.compile(Empty.PATTERN), Empty.parse)
])

TEXT_PATTERNS = OrderedDict([
    (re.compile(Tag.PATTERN), Tag.parse),
    (re.compile(Text.PATTERN), Text.parse)
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
                try:
                    current, linenumber = PATTERNS[pattern](
                        match, current, linenumber)
                except ParserException as exc:
                    exc.tree = tree
                    raise exc
                found = True
                break
        if not found:
            raise ParserException(
                "No matching syntax element found!", linenumber, tree=tree)
    if current is not tree:
        raise ParserException(
            "Du hast vergessen, Klammern zu schließen! (die öffnende ist in "
            "Zeile {})".format(
                current.linenumber), linenumber=current.linenumber, tree=tree)
    return tree


def main(test_file_name=None):
    source = ""
    test_file_name = test_file_name or "source0"
    with open("test/{}.txt".format(test_file_name)) as f:
        source = f.read()
    try:
        tree = parse(source)
        print(tree.dump())
    except ParserException as e:
        print(e)
    else:
        print("worked!")


if __name__ == "__main__":
    test_file_name = sys.argv[1] if len(sys.argv) > 1 else None
    exit(main(test_file_name))
