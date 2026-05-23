.PHONY: install run run-skip-extract dry-run test clean

install:
	pip install -r requirements.txt

run:
	cd $(shell pwd) && python src/pipeline.py

run-skip-extract:
	cd $(shell pwd) && python src/pipeline.py --skip-extract

dry-run:
	cd $(shell pwd) && python src/pipeline.py --dry-run

test:
	cd $(shell pwd) && python -m pytest tests/ -v --tb=short

clean:
	rm -rf data/raw/*.json data/processed/*.db logs/*.log
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
