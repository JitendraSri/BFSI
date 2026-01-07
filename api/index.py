from app import app

# Vercel will treat this file as a serverless function entrypoint.
# Export a WSGI-compatible callable; using both names is safe.
application = app


