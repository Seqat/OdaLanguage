.PHONY: test

PYTHON ?= python3
ODA_TEST_CFLAGS ?= -fsanitize=address -g

test:
	ODA_TEST_CFLAGS="$(ODA_TEST_CFLAGS)" $(PYTHON) -m pytest tests
