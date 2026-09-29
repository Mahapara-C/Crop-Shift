/* CropShift website config. The API_BASE line is the one to change.
   - A URL: the live API (the free server sleeps; the page shows "waking up").
   - "mock": read the example files in web/mock/ instead (serve the web/ folder,
     then open /app/, so ../mock/*.json can be found).
   For testing, ?api=<url or mock> in the page address overrides it. */
window.API_BASE = "https://cropshift-api-eg28.onrender.com/";
try { const o = new URLSearchParams(location.search).get("api"); if (o) window.API_BASE = o; } catch (e) {}
