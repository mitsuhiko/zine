from sphinxcontrib.serializinghtml import PickleHTMLBuilder


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
    app.setup_extension('sphinxcontrib.serializinghtml')
    app.add_builder(WebBuilder)
    return {
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
