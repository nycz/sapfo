
.PHONY: test
test:
	@pytest


.PHONY: mypy
mypy:
	@mypy --strict --pretty -p sapfo


.PHONY: coverage
coverage:
	@pytest --cov=sapfo


.PHONY: coverage-report
coverage-report:
	@pytest --cov=sapfo --cov-report=html
