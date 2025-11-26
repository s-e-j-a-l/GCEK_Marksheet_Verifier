from app import app
import os

if __name__ == "__main__":
    # Render provides the port in the PORT environment variable
    port = int(os.environ.get("PORT", 5000))

    # Bind to 0.0.0.0 so Render can access your service
    app.run(host="0.0.0.0", port=port)
