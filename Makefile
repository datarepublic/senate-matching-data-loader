init:
	pipenv install

test: go
	pipenv run python -m unittest tests/units.py
	pipenv run python ./tests/integration.py

go:
	go get golang.org/x/text/width
	go build -o tonarrow -i toNarrow.go

.PHONY: init test go