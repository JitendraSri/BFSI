# FinRAG AI — Next.js Frontend

A modern **Next.js 16 + React 19 + TypeScript** client for the FinRAG AI / BFSI Intelligence platform. It is an alternative single-page frontend to the server-rendered Jinja templates in the parent project, talking to the same Flask API over JWT-authenticated REST and Server-Sent Events.

> The Flask backend (`../app.py`) is the source of truth for all data and AI features. This app is purely a client — it ships no business logic of its own.

## Stack

| Concern | Choice |
|---|---|
| Framework | Next.js 16.4 (App Router) |
| UI library | React 19.3 |
| Language | TypeScript 5 |
| Styling | Tailwind CSS v4 (`@tailwindcss/postcss`) |
| Primitives | Radix UI (dialog, dropdown-menu, switch, tooltip) |
| Icons | lucide-react |
| Charts | Recharts 3 |
| Theming | next-themes (light / dark) |
| Class utils | class-variance-authority, clsx, tailwind-merge |

## Getting started

The backend must be running first (default `http://127.0.0.1:5000` — see the parent [README](../README.md)).

```bash
# from this frontend/ directory
npm install

# point the client at the Flask API
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:5000" > .env.local

npm run dev
```

Open **http://localhost:3000**.

| Script | Purpose |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint (`eslint-config-next`) |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `""` (same origin) | Base URL of the Flask backend. Set to `http://127.0.0.1:5000` in local dev |

## How it talks to the backend

All backend calls go through [`src/lib/api.ts`](src/lib/api.ts):

- **`apiFetch<T>(path, options)`** — JSON fetch that attaches `Authorization: Bearer <token>` from `localStorage`, and on a `401` clears the token and redirects to `/login`.
- **`apiStream(path, body, onStage, onToken, signal)`** — reads the FinRAG `text/event-stream`, dispatching `stage`, `token`, `done` and `error` events so answers render token-by-token with live stage labels. An `AbortSignal` cancels an in-flight answer.

Authentication state is held in [`src/contexts/AuthContext.tsx`](src/contexts/AuthContext.tsx); the JWT lives in `localStorage` exactly as the Jinja app expects, so the two frontends are interchangeable against one backend.

## Routes

| Route | Page |
|---|---|
| `/` | Landing (redirects into the app) |
| `/login`, `/register` | Authentication |
| `/dashboard` | Metric cards and charts (Recharts) |
| `/transactions` | Paginated, filterable ledger |
| `/upload` | Transaction file import |
| `/fraud-alerts` | Flagged-transaction investigation queue |
| `/predictive` | Risk simulator and training history |
| `/insights` | Model and FinRAG benchmark metrics |
| `/investments` | Holdings and allocation |
| `/loans` | EMI and affordability calculator |
| `/credit-score` | Credit-score simulator |
| `/rag` | FinRAG Copilot — streaming document Q&A |
| `/profile` | Account settings |

Shared chrome lives in [`src/components/layout/`](src/components/layout/) (`AppLayout`, `Sidebar`, `Topbar`).

## Project layout

```
frontend/
├── src/
│   ├── app/              # App Router pages (one folder per route)
│   ├── components/layout/ # AppLayout, Sidebar, Topbar
│   ├── contexts/         # AuthContext (JWT + current user)
│   └── lib/              # api.ts (fetch + SSE), utils.ts
├── public/               # static SVGs
├── next.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

`node_modules/`, `.next/` and `out/` are git-ignored build artifacts and are not committed.
