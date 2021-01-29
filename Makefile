PKGDIR = sapfo


# Formatting

.PHONY: isort
isort:
	isort ${PKGDIR}


# Linting

.PHONY: vulture
vulture:
	-vulture whitelist.py ${PKGDIR}

.PHONY: flake8
flake8:
	-flake8 --statistics ${PKGDIR}

.PHONY: mypy
mypy:
	-mypy --strict --pretty -p ${PKGDIR}

.PHONY: check
check: mypy flake8 vulture


# Testing

.PHONY: test
test:
	@pytest

.PHONY: coverage
coverage:
	@pytest --cov=${PKGDIR}

.PHONY: coverage-report
coverage-report:
	@pytest --cov=${PKGDIR} --cov-report=html
