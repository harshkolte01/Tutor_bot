# Frontend (HTML/CSS/JS)

## Structure

- `index.html` - public landing page
- `pages/login.html` - sign in page
- `pages/signup.html` - account registration page
- `components/api_client.js` - centralized backend API client
- `components/session.js` - browser auth session storage
- `assets/css/` - shared and page-level styles
- `assets/js/` - page scripts

## Run Locally

```bash
cd frontend
python -m http.server 5500
```

Then open `http://localhost:5500`.

## API Base URL

Frontend reads `window.TUTOR_BOT_CONFIG.API_BASE_URL` from `config.js`.
Default is `http://localhost:5000`.
