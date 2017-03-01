#!/bin/bash
celery -A server.celery worker --loglevel=debug --concurrency=1
