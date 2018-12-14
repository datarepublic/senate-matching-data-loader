init:
	pip install - requirements.txt

test:
	python -m unittest tests/units.py
	python ./tests/integration.py

.PHONY: init test
