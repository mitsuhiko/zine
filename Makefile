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
