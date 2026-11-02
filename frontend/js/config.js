/* =====================================================================
   Deployment config. Points the frontend at the backend's API origin.
   Loaded before api.js on every page.

   Blank on purpose: this app deploys as one Vercel project serving both
   the static frontend and the FastAPI backend (api.js's own fallback is
   `window.location.origin`, i.e. "call whatever host served this page").
   A separate API_BASE_URL is only needed if the frontend and backend are
   ever split across two different hosts again.
   ===================================================================== */
window.API_BASE_URL = "";
