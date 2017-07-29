.PHONY: test

test:
		rm -rf ./data/output/*
		tox

default: test
