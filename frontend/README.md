# الواجهة الأمامية | Frontend

واجهة عربية RTL لنظام السجل المدني — React 19 + TypeScript + Vite + Tailwind 4 +
TanStack Query + react-router.

## التشغيل | Running

```bash
npm install        # or: make install-fe
npm run dev        # Vite on :5173, proxying /api to http://localhost:8010
```

للتشغيل داخل Docker مع بقية النظام:

```bash
make up            # db + backend + nginx frontend on :8090
```

## الأوامر | Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | dev server with HMR and an `/api` proxy |
| `npm run lint` | oxlint |
| `npm run build` | `tsc -b` (typecheck) then `vite build` |

`npm run build` is the gate in CI; it fails on any type error.

## البنية | Layout

```
src/lib/       api client (axios, silent token refresh), API types
src/auth/      AuthContext, login + forced password change, route guard
src/layout/    AppShell: RTL sidebar, role-aware navigation
src/pages/     Dashboard, Persons list, placeholders for unbuilt sections
nginx.conf     production server: serves dist/ and proxies /api to backend
```

All sections are listed in the sidebar from day one; those not built yet say so
explicitly rather than returning 404.

See [../docs/DECISIONS.md](../docs/DECISIONS.md) for why the API is proxied
same-origin instead of via CORS, and why tokens currently live in
`localStorage`.
