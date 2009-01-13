from sphinx.builders.html import PickleHTMLBuilder


class WebBuilder(PickleHTMLBuilder):
    name = "webpickle"
    add_permalinks = False

    def get_target_uri(self, docname, type=None):
        if docname == 'index' or docname.endswith('/index'):
            docname = docname[:-5]
        return docname or '.'

    def prepare_writing(self, docnames):
        PickleHTMLBuilder.prepare_writing(self, docnames)
        self.docsettings.initial_header_level = 2


def setup(app):
    app.add_builder(WebBuilder)
