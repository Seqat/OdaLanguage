.PHONY: test test-asan

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ODA_TEST_CFLAGS ?= -fsanitize=address -g

test:
	ODA_TEST_CFLAGS="$(ODA_TEST_CFLAGS)" $(PYTHON) -m pytest tests

test-asan:
	ODA_TEST_CFLAGS="-fsanitize=address -g" $(PYTHON) -m pytest tests
