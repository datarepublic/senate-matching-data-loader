init:
	pipenv install

test:
	python -m unittest tests/units.py
	python ./tests/integration.py

go:
	go get golang.org/x/text/width
	go build -o tonarrow -i toNarrow.go

.PHONY: init test go
