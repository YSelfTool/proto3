#!/usr/bin/env python3
import regex as re
import os
import sys

ROUTE_PATTERN = r'@(?:[[:alpha:]])+\.route\(\"(?<url>[^"]+)"[^)]*\)\s*(?:@[[:alpha:]_()., ]+\s*)*def\s+(?<name>[[:alpha:]][[:alnum:]_]*)\((?<params>[[:alnum:], ]*)\):'
quote_group = "[\"']"
URL_FOR_PATTERN = r'url_for\({quotes}(?<name>[[:alpha:]][[:alnum:]_]*){quotes}'.format(quotes=quote_group)

ROOT_DIR = "."
ENDINGS = [".py", ".html", ".txt"]
MAX_DEPTH = 2

def list_dir(dir, level=0):
    if level >= MAX_DEPTH:
        return
    for file in os.listdir(dir):
        path = os.path.join(dir, file)
        if os.path.isfile(path):
            if file == sys.argv[0]:
                continue
            for ending in ENDINGS:
                if file.endswith(ending):
                    yield path
        elif os.path.isdir(path):
            yield from list_dir(path, level+1)

class Route:
    def __init__(self, file, name, parameters):
        self.file = file
        self.name = name
        self.parameters = parameters

    def __repr__(self):
        return "Route({file}, {name}, {parameters})".format(
            file=self.file, name=self.name, parameters=self.parameters)

    def get_parameter_set(self):
        return {parameter.name for parameter in self.parameters}

class Parameter:
    def __init__(self, name, type=None):
        self.name = name
        self.type = type

    def __repr__(self):
        return "Parameter({name}, {type})".format(name=self.name, type=self.type)

    @staticmethod
    def from_string(text):
        if ":" in text:
            type, name = text.split(":", 1)
            return Parameter(name, type)
        return Parameter(text)

def split_url_parameters(url):
    params = []
    current_param = None
    for char in url:
        if current_param is None:
            if char == "<":
                current_param = ""
        else:
            if char == ">":
                params.append(Parameter.from_string(current_param))
                current_param = None
            else:
                current_param += char
    return params

def split_function_parameters(parameters):
    return list(map(str.strip, parameters.split(",")))

def read_url_for_parameters(content):
    params = []
    bracket_level = 1
    current_param = None
    for char in content:
        if bracket_level == 0:
            if current_param is not None:
                params.append(current_param.split("=")[0].strip())
            return params
        if char == ",":
            if current_param is not None:
                params.append(current_param.split("=")[0].strip())
            current_param = ""
        else:
            if current_param is not None:
                current_param += char
            if char == "(":
                bracket_level += 1
            elif char == ")":
                bracket_level -= 1

class UrlFor:
    def __init__(self, file, name, parameters):
        self.file = file
        self.name = name
        self.parameters = parameters

    def __repr__(self):
        return "UrlFor(file={file}, name={name}, parameters={parameters})".format(
            file=self.file, name=self.name, parameters=self.parameters)

routes = {}
url_fors = []
for file in list_dir(ROOT_DIR):
    with open(file, "r") as infile:
        content = infile.read()
        for match in re.finditer(ROUTE_PATTERN, content):
            name = match.group("name")
            function_parameters = split_function_parameters(match.group("params"))
            url_parameters = split_url_parameters(match.group("url"))
            routes[name] = Route(file, name, url_parameters)
        for match in re.finditer(URL_FOR_PATTERN, content):
            name = match.group("name")
            begin, end = match.span()
            parameters = read_url_for_parameters(content[end:])
            url_fors.append(UrlFor(file=file, name=name, parameters=parameters))

for url_for in url_fors:
    if url_for.name not in routes:
        print("Missing route '{}' (for url_for in '{}')".format(url_for.name, url_for.file))
        continue
    route = routes[url_for.name]
    route_parameters = route.get_parameter_set()
    url_parameters = set(url_for.parameters)
    if len(route_parameters ^ url_parameters) > 0:
        print("Parameters not matching for '{}' in '{}:'".format(url_for.name, url_for.file))
        only_route = route_parameters - url_parameters
        only_url = url_parameters - route_parameters
        if len(only_route) > 0:
            print("Only in route: {}".format(only_route))
        if len(only_url) > 0:
            print("Only in url: {}".format(only_url))
