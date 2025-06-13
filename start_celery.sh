#!/bin/bash
uv run celery -A server.celery worker --loglevel=debug --concurrency=1
