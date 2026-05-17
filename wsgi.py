"""WSGI entry point for Gunicorn on Render."""
from dotenv import load_dotenv

load_dotenv()

from app import app as application  # noqa: E402
