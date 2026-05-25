# Product images on Render (persistent uploads)

Uploads are stored under `static/uploads/` (products, profiles, etc.). Without persistent storage, **every deploy deletes uploaded photos** while the database still lists old paths.

## What we configured

- `render.yaml` mounts a **1 GB persistent disk** at:
  `/opt/render/project/src/static/uploads`
- Code saves files via `upload_storage.py` using `UPLOAD_FOLDER` from config.

## After deploy

1. Open `https://sports-outdoors.onrender.com/health`
2. Check `"uploads_persistent_disk": true` — disk is mounted correctly.
3. If `false`, in Render Dashboard → your Web Service → **Disks** → add disk:
   - Mount path: `/opt/render/project/src/static/uploads`
   - Size: 1 GB (or more)

## Images lost before this fix

Files removed by earlier deploys are **not recoverable** from git. Re-upload product photos once; new uploads will survive future commits/deploys.

## Local development

No disk needed. Files go to `ecommerce_system/static/uploads/` on your PC.
