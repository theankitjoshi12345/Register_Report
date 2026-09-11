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
