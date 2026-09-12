# React islands

Four pages (Physics Lab, Lesson Builder, Teacher Analytics, Student Tutor)
have a small, additive React-rendered panel layered onto their existing
Django templates. This document explains what that is, why it's built the
way it is, and — importantly — **what has and hasn't actually been run**.

## Status: built and smoke-tested, not browser-tested

This was first authored in a development environment with no Node.js/npm
installed (an unverified first draft), then a portable Node.js was fetched
and used to actually `npm install`, build, and exercise every bundle:

- `npm run build` succeeds and produces real, working bundles at
  `static/react/*.js` (committed to the repo as of this writing — not
  placeholders; see below for what happens if they ever need regenerating).
- `npm run smoke-test` loads each built bundle into a simulated DOM (jsdom)
  together with the real vendored React/ReactDOM UMD runtime and a
  realistic bootstrap payload, and confirms: no thrown error, the mount
  reveals itself (the `useEffect` ran), and — for Student Tutor and Lesson
  Builder — that a real user interaction (submitting the ask form, clicking
  Delete) runs its fetch-based handler with no thrown error against a
  mocked `fetch`.

That is real execution of the real code, and it did catch a real bug (see
"Bugs this caught" below) — but jsdom is not a browser. Layout, CSS,
`ResizeObserver`, actual network behaviour against the live Django server,
and how it all looks are still unverified; see the bottom of this document
for the precise, current boundary.

## Design philosophy: additive, never destructive

Every island is designed so a broken, missing, or reverted-to-placeholder
bundle **cannot make a page worse than it already is** — this was the
guiding rule while the JS was still completely unverified, and it's kept
even now that it's been built and smoke-tested, because the committed
bundle can still drift from a page's HTML over time:

- **Physics Lab, Teacher Analytics, Lesson Builder** — the React panel
  mounts into its own `<section ... hidden>` and only removes `hidden`
  itself, inside a `useEffect`, once it has actually rendered. It is purely
  additive: it never hides or replaces the existing server-rendered content
  around it. If the bundle 404s, throws, or is a placeholder stub, the
  section just never appears — everything else on the page is exactly as it
  was before this work.
- **Student Tutor** — the one island that *does* replace something (the
  conversation panel, for a live chat instead of a full-page reload per
  turn). The existing panel is marked `data-tutor-static` and is only hidden
  from inside the React component's `useEffect`, i.e. only after a
  successful mount. Same rule: any failure leaves the plain HTML form and
  thread fully working, exactly as today.

None of the five existing Physics Lab scripts (`lab.js`, `kinematics.js`,
`experiment-flow.js`, `lab-instrument.js`, `kinematics-3d.js`) were touched,
and the Physics Lab island never attaches to their forms — it only renders a
read-only reference card, to avoid two things listening to the same submit
event.

## Backend: same views, one more response format

No new API layer, no new authentication, no new CSRF exemption. Each of the
four existing views now branches on `config.react_bridge.wants_json(request)`
— true only when the request carries `X-HANAI-Client: react`, a header only
these bundles ever send. Every existing caller (a normal browser form POST,
the Django test suite, curl) never sends it and sees byte-identical old
behaviour. When it *is* present, the view returns a small `JsonResponse`
carrying the same data (and running through the same service functions, the
same owner/permission checks, the same CSRF middleware) instead of doing an
HTTP redirect or a full HTML re-render.

The initial data each island needs is embedded straight into the page HTML
as a JSON-valued `data-state` attribute (the same pattern this codebase
already used for `scenarios_json` on the Kinematics page) — no extra
request, no extra query, just a JSON projection of context the view had
already computed.

## Build tooling

```
frontend/
  package.json       react, react-dom (pinned to match the vendored UMD
                      runtime), vite, @vitejs/plugin-react, jsdom (dev-only)
  build.mjs           builds each island as its own independent bundle
                      (see "Why build.mjs and not vite.config.js" below)
  smoke-test.mjs      loads every built bundle into jsdom and exercises it
  src/shared/         csrf.js (fetch + CSRF header helper), mount.js
                      (bootstrap-JSON reader + safe mount)
  src/lab/            Physics Lab island (read-only reference card)
  src/lesson-builder/ Lesson Builder island (activity list + delete)
  src/analytics/      Teacher Analytics island (sortable explorer)
  src/tutor/          Student Tutor island (live chat)
```

React/ReactDOM are **not** bundled — they're vendored UMD builds at
`static/js/vendor/react-18.3.1.production.min.js` /
`react-dom-18.3.1.production.min.js` (same MIT-vendoring pattern as
Three.js; see that directory's README), loaded once per page as plain
globals, with `external`/`globals` Rollup options pointing at them. Every
page therefore shares one copy of the React runtime instead of bundling
four.

### Why `build.mjs` and not a single `vite.config.js`

The first draft used one `vite.config.js` with all four entries and
`output.format: "iife"`. That does not work: Rollup refuses IIFE/UMD output
for a "code-splitting" build with more than one input, even when the inputs
share no code (`Invalid value "iife" for option "output.format" - UMD and
IIFE output formats are not supported for code-splitting builds`). This was
only discovered once an actual build was run. `build.mjs` instead calls
Vite's JS API once per island, each a fully independent single-entry IIFE
build — four separate, simple bundles instead of one multi-entry one.

### To build and verify it

```powershell
cd frontend
npm install
npm run build          # -> static/react/*.js
npm run smoke-test      # loads them in jsdom and exercises them
# or both:
npm run verify
```

### The committed bundles

`static/react/*.js` are committed to the repo as real, built, smoke-tested
bundles (not placeholders) as of this writing. If `frontend/src` changes and
nobody rebuilds, `manage.py collectstatic` and every page render still work
fine — they'll just keep serving the older, still-valid bundle. Only if
`static/react/*.js` were ever deleted entirely (or intentionally reset to a
minimal placeholder) would `DJANGO_MANIFEST_STATIC=1` collectstatic need
that path to exist at all; the Dockerfile's `frontend` build stage
regenerates them from source on every image build regardless, and is
designed to never fail the image build even if `npm install`/`npm run
build`/`npm run smoke-test` fail (see the comments in `Dockerfile`).

## Bugs this caught

Running the actual build immediately surfaced the `vite.config.js`
multi-entry/IIFE incompatibility above — exactly the class of bug "written
but never run" warned it couldn't catch. `npm audit` also flags a
moderate/high advisory in `esbuild`/`vite`'s bundled dev server
(GHSA-67mh-4wv8-2f99); it only affects `vite dev`'s local dev server, which
this project never runs (only `vite build`, via `build.mjs`), so it doesn't
apply to how this is used, but `npm audit fix --force` (a breaking upgrade
to Vite 6) is available if it's ever worth taking.

## What was actually verified, and what wasn't

**Verified**: every Django view change (full `manage.py test`, `check`,
`check --deploy`, `makemigrations --check`, `collectstatic` under both
normal and `DJANGO_MANIFEST_STATIC=1` storage, manual `runserver` requests
including a page render under manifest storage with the real bundle path
resolved); `npm install` and `npm run build` actually succeeding; all four
bundles loading and mounting with no thrown error in a simulated DOM
(jsdom) using the real vendored React/ReactDOM runtime; the reveal-after-
mount / hide-static-content behaviour actually firing; the Student Tutor
"ask" form submit and the Lesson Builder "Delete" click each running their
real fetch-based handler against a mocked `fetch` with no thrown error.

**Not verified**: anything in a real browser -- actual layout/CSS, real
network requests against a live Django server end-to-end, real user
interaction, mobile/responsive behaviour, or cross-browser behaviour. jsdom
approximates a DOM; it is not Chrome, Firefox, or Safari.
