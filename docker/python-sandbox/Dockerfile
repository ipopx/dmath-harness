# Ephemeral math sandbox for the run_python agent tool.
# Build: docker build -t dmath-python-sandbox:latest docker/python-sandbox
FROM python:3.12-slim

RUN pip install --no-cache-dir "numpy>=1.26,<3" "sympy>=1.12,<2"

WORKDIR /sandbox
# Code is fed on stdin via: docker run ... python -u -
CMD ["python", "-u", "-"]
