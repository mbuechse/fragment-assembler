#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Assemble (bilingual) web pages from HTML fragments.

Based on three main concepts:
* Context
* "expressions"
* Interpreter

The Context is a dictionary of HTML fragments (indexed by strings) with fallback ("parent") Context.
The HTML fragments may contain "expressions" enclosed in section (§) symbols, e.g., §bla(blubb, foo(bar))§
Operations (such as "bla" and "foo") are translated into method calls on the Interpreter, i.e.,
interpreter.bla(context, "blubb", interpreter.foo(context, "bar")). In addition to HTML fragments, the
context can also store the current language, the name of the current page, etc.

I recommend partitioning any HTML page into the following fragments:
* the scaffolding -- here called page_de and page_en --, with variables for title, description, actual content,
  navigation bars, and scripts;
* the content -- here called main;
* scripts -- here called script;
* navigation bars.

The content (and maybe some scripts) is the only fragment that is really unique to each page.

The navigation bars can easily be computed using a few auxiliary fragments:
* the scaffolding -- here called nav_skeleton;
* selected entry -- here called nav_active;
* normal entry -- here called nav_normal.

Everything that is unqiue to a page is recorded in a file called pages.json. Moreover, there are
files dict_en.json and dict_de.json that provide English and German names for some variables
(currently: month names).

Matthias Büchse
Dresden, 2015

Licence: GPL
"""

import io
import json
import shutil
import subprocess
import sys


class Context(object):
    def __init__(self, parent=None, fragments=None):
        self.parent = parent
        self.fragments = fragments if fragments is not None else {}

    def put(self, key, frag):
        self.fragments[key] = frag

    def get(self, key):
        if key in self.fragments:
            return self.fragments[key]
        elif self.parent is not None:
            return self.parent.get(key)
        else:
            raise KeyError


class ExpressionParser(object):
    """An expression is either
    * atomic: it does not contain parentheses or commas,
    * composite: it has the form  atomic(expr, ..., expr)

    Given a Context context and an object interpreter, this parser performs the following function eval:
    * eval(atomic) = atomic
    * eval(atomic(expr1, ..., exprk)) = interpreter.atomic(context, eval(expr1), ..., eval(exprk))
    """
    def __init__(self, interpreter, context, expression):
        self.interpreter = interpreter
        self.expression = expression
        self.context = context
        self.idx = 0
        self.len_ = len(expression)

    def parse(self):
        i = self.idx
        e = self.expression
        l = self.len_
        while i < l and e[i] not in "(,)":
            i += 1
        v = e[self.idx:i].strip()
        if i == l:
            self.idx = i
            return v
        elif e[i] == ',':
            self.idx = i + 1
            return v
        elif e[i] == ')':
            self.idx = i
            return v
        else:  # e[i] == '('
            self.idx = i + 1
            args = []
            while self.idx < l and e[self.idx] != ')':
                args.append(self.parse())
            return getattr(self.interpreter, v)(self.context, *args)


def interpret(interpreter, context, fragment_text):
    """Evaluate expressions in fragment_text. Every occurrence of §expr§ is replaced by
    ExpressionParser(interpreter, context, "expr").parse()."""
    output = []
    it = iter(fragment_text.split(u"§"))
    try:
        while True:
            output.append(next(it))
            output.append(ExpressionParser(interpreter, context, next(it)).parse())
    except StopIteration:
        pass
    return u"".join(output)


class Interpreter(object):
    """Most basic interpreter."""
    def include(self, context, key):
        return interpret(self, context, context.get(key))

    def include_conditional(self, context, key):
        try:
            return self.include(context, key)
        except KeyError:
            return u""

    def sec(self, context):
        return u"§"

    def var(self, context, key):
        try:
            return context.get(key)
        except KeyError:
            return u""


LANG_TO_PROJ = {'de': lambda de, en: de, 'en': lambda de, en: en}
ACTIVENESS_TO_KEY = {True: "nav_active", False: "nav_normal"}


class MyInterpreter(Interpreter):
    """Adds navigation bars and localization."""
    def __init__(self, pages, dic, navbar_types, **kwargs):
        super(MyInterpreter, self).__init__(**kwargs)
        self.pages = pages
        self.navbar_types = navbar_types
        self.dic_ = dic

    def dic(self, context, key):
        return self.dic_[context.get("lang")][key]

    def localize(self, context, de, en):
        return LANG_TO_PROJ[context.get("lang")](de, en)
        # more allocations: return {'de': de, 'en': en}[context.get("lang")]

    def nav_bar(self, context, lang, type_, nav_bars):
        """Inserts a single navigation bar into nav_bars"""
        nav = []
        for page in self.pages:
            # "nav" determines on which navigation bars a page is shown, and how it should be referred to
            if "nav" in page and type_ in page["nav"]:
                c = Context(context, {"navtitle": page["nav"][type_][lang], "navhref": page["file_" + lang]})
                nav.append(self.include(c, ACTIVENESS_TO_KEY[context.get("active")[type_] == page["id"]]))
        nav_bars.append(self.include(Context(context, {"nav": u"".join(nav)}), "nav_skeleton"))

    def nav(self, context, lang):
        """Computes navigation bars for current page"""
        nav = []
        # active determines which navigation bars ("types") are visible on a page
        types = context.get("active")
        for type_ in self.navbar_types:  # do not use types directly; order should be determined by navbar_types
            if type_ in types:
                self.nav_bar(context, lang, type_, nav)
        return u"".join(nav)


def load(fn):
    with io.open(fn, encoding="utf-8") as f:
        return f.read()


def load_conditional(fn):
    try:
        return load(fn)
    except IOError:
        return u""


def load_json(fn):
    with io.open(fn, encoding="utf-8") as f:
        return json.load(f)


def save(fn, text):
    with io.open(fn, 'w', encoding="utf-8") as f:
        f.write(text)


def minify_html(src, dst):
    # invoke html-minifier tool by Zoltan Frombach (requires node.js)
    sys.stderr.write("minifying {0} -> {1}".format(src, dst))
    retcode = subprocess.call(["html-minifier", "-c", "minify.json", "-o", dst, src])
    if retcode:
        sys.stderr.write(" FAILED with return code {0:n}.\nMoving file instead.".format(retcode))
        shutil.move(src, dst)
    sys.stderr.write("\n")


FRAG = "fragments/"
CONTENT = "content/"
DEPLOY = "deploy/"
LANGUAGES = ["de", "en"]
DO_MINIFY = False
if DO_MINIFY:
    MINIFIER = minify_html
else:
    MINIFIER = shutil.move


def main():
    dic = {}
    for lang in LANGUAGES:
        dic[lang] = load_json("dict_{0}.json".format(lang))
    pages = load_json("pages.json")

    c_global = Context(None, {"page_de": load(FRAG + "page_de.html"),
                              "page_en": load(FRAG + "page_en.html"),
                              "nav_skeleton": load(FRAG + "nav_skeleton.html"),
                              "nav_active": load(FRAG + "nav_active.html"),
                              "nav_normal": load(FRAG + "nav_normal.html"),
                              "description_de": load(FRAG + "description_de").split('\n')[0],
                              "description_en": load(FRAG + "description_en").split('\n')[0]})

    inter = MyInterpreter(pages, dic, navbar_types=["main"])
    for page in pages:
        extra = {"script": load_conditional(CONTENT + page["id"] + ".script.html")}
        if "load" in page:
            for l in page["load"]:
                extra[l] = load(CONTENT + l + ".html")
        extra.update(page)
        c_page = Context(c_global, extra)

        main_ = load_conditional(CONTENT + page["id"] + ".html")
        subnav = load_conditional(CONTENT + page["id"] + ".subnav.html")
        for lang in LANGUAGES:
            main_l = main_ or load(CONTENT + page["id"] + "." + lang + ".html")
            subnav_l = subnav or load_conditional(CONTENT + page["id"] + ".subnav." + lang + ".html")
            c_localized = Context(c_page, {"main": main_l, "lang": lang, "subnav": subnav_l})
            save("/tmp/minify_me.html", inter.include(c_localized, "page_" + lang))
            MINIFIER("/tmp/minify_me.html", DEPLOY + page["file_" + lang])


if __name__ == "__main__":
    main()