# Product images (persistent on Render)

Uploads are stored in **Supabase Storage** when configured (recommended). Files survive every git push / Render redeploy. Local disk is only a fallback for development.

## One-time setup (Supabase)

You already use Supabase for `DATABASE_URL`. Add storage:

1. [Supabase Dashboard](https://supabase.com/dashboard) → your project → **Storage**
2. Create bucket **`product-images`** (or match `SUPABASE_STORAGE_BUCKET`)
3. Set bucket to **Public**
4. **Project Settings → API** → copy **`service_role`** key (secret)

## Render environment variables

In Render → **sports-outdoors** → **Environment**:

| Variable | Value |
|----------|--------|
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` (service_role secret) |
| `SUPABASE_STORAGE_BUCKET` | `product-images` (optional, this is the default) |
| `SUPABASE_URL` | Optional — auto-derived from `DATABASE_URL` if omitted |

Redeploy after saving.

## Verify

Open: `https://sports-outdoors.onrender.com/health`

```json
"product_image_storage": "supabase",
"supabase_storage_configured": true
```

If `supabase_storage_configured` is **false**, images still use local disk and **will be lost** on redeploy until you add the service role key.

## After setup

1. **Re-upload** product photos (old files on Render disk are gone).
2. New uploads get a `https://....supabase.co/storage/...` URL in the database.
3. Web and mobile both load that URL — no extra mobile config.

## Local development

Without `SUPABASE_SERVICE_ROLE_KEY`, files save to `static/uploads/products/` on your PC (normal dev behavior).
