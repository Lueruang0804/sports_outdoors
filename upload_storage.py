"""
Central upload paths for product images and other user files.

On Render, mount a persistent disk at static/uploads (see render.yaml) so files
survive redeploys. Locally, files live under the project's static/uploads/ folder.
"""

from __future__ import annotations

import os

# Subfolders under static/uploads — DB stores uploads/<subdir>/<file>
UPLOAD_SUBDIRS = ('products', 'profiles', 'documents', 'advertisements', 'pod')


def project_root() -> str:
    return os.path.abspath(os.path.dirname(__file__))


def get_upload_root(app=None) -> str:
    """Absolute path to the uploads root (static/uploads)."""
    if app is not None:
        return os.path.abspath(app.config['UPLOAD_FOLDER'])
    env = os.environ.get('UPLOAD_FOLDER', '').strip()
    if env:
        return os.path.abspath(env)
    try:
        from flask import current_app
        return os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    except RuntimeError:
        return os.path.join(project_root(), 'static', 'uploads')


def subdir_abs(subdir: str, app=None) -> str:
    if subdir not in UPLOAD_SUBDIRS:
        raise ValueError(f'Unknown upload subdir: {subdir}')
    path = os.path.join(get_upload_root(app), subdir)
    os.makedirs(path, exist_ok=True)
    return path


def db_relative_path(subdir: str, filename: str) -> str:
    """Value stored in image_url / profile_picture (no leading slash)."""
    return f'uploads/{subdir}/{filename}'


def abs_path_from_db_value(db_value: str | None) -> str | None:
    """Resolve DB path uploads/products/x.jpg to absolute filesystem path."""
    if not db_value or not str(db_value).strip():
        return None
    url = str(db_value).replace('\\', '/').strip().lstrip('/')
    if url.startswith('static/'):
        url = url[len('static/') :]
    if url.startswith('uploads/'):
        return os.path.join(project_root(), 'static', url)
    return os.path.join(project_root(), 'static', 'uploads', url)


def ensure_upload_dirs(app=None) -> None:
    root = get_upload_root(app)
    os.makedirs(root, exist_ok=True)
    for name in UPLOAD_SUBDIRS:
        os.makedirs(os.path.join(root, name), exist_ok=True)


def uploads_on_render_disk() -> bool:
    """True when Render persistent disk is mounted at the uploads root."""
    if not os.environ.get('RENDER', '').strip():
        return False
    root = get_upload_root()
    return os.path.isdir(root) and os.path.ismount(root)
