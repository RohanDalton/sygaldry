.PHONY: lint

lint:
	black sygaldry
	flake8 sygaldry
	isort sygaldry
	mypy sygaldry