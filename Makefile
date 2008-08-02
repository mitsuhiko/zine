.PHONY: help clean server shell reset extract-messages

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  clean                 delete all compiled python and backup files"
	@echo "  server                start the development server"
	@echo "  shell                 start a development shell"
	@echo "  extract-messages      update the pot file"
	@echo "  update-translations   update the translations"
	@echo "  compile-translations  compile all translation files"

clean:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

server:
	@(python textpress-management.py runserver)

shell:
	@(python textpress-management.py shell)

reset:
	@(sh reset.sh)

extract-messages:
	pybabel extract -F babel.ini -k lazy_gettext -k lazy_ngettext -o textpress/i18n/messages.pot .

update-translations:
	pybabel update -itextpress/i18n/messages.pot -dtextpress/i18n -Dmessages

compile-translations:
	pybabel compile -dtextpress/i18n --statistics
	python textpress/i18n/compilejs.py
