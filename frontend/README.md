# Register Report frontend

React and TypeScript, built with Vite and styled with Tailwind CSS. The app provides
session login, store selection, a five-step close form, saved report history, and
editing. See the [project README](../README.md) for setup and business rules.

```sh
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite forwards `/api`, `/admin`, and Django's `/static`
assets to <http://127.0.0.1:8000>. Start Django and create an administrator with
`make admin` from the project root to sign in. Additional users and store
memberships are managed in Django admin.

```sh
npm run lint
npm test
npm run build
```

Interaction tests exercise the React app in a simulated DOM, including the close
steps, save/edit flows, errors, and authenticated store access.

`npm run preview` serves the production build at <http://127.0.0.1:4173>. It does
not provide the Django API; deployment must route `/api` to Django on the same
origin.

For a Vercel deployment with Django hosted separately, add
`VITE_API_BASE_URL=https://your-django-api.example.com` in the Vercel project
environment variables. Use the Django origin only, without `/api` or a trailing
slash. Configure the backend's allowed hosts, CSRF trusted origin, CORS origin,
and cross-site cookies for the exact Vercel HTTPS domain. See the root
[deployment instructions](../README.md#vercel-and-production-deployment).
