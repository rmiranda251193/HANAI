# Vendored front-end libraries

These files are committed as-is (no build step, no npm). They are served by
Django's staticfiles / WhiteNoise like any other static asset and are hashed by
`collectstatic` in production.

## three-0.160.1.module.min.js

- **Library:** Three.js
- **Version:** r160.1 (`three@0.160.1`)
- **Format:** native ES module (`import * as THREE from "three"` via the import
  map declared in `templates/physics/kinematics.html`)
- **License:** MIT (`SPDX-License-Identifier: MIT`, header retained in the file)
- **Source:** https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.module.min.js
- **SHA-256:** `3E690AC7D180B0AADF0891BEA39EEC643E29E2D3E75C99B18689518665F69BA6`

Only the core `three` module is vendored. No `examples/jsm` add-ons are used;
orbit/zoom/pan camera control is a small hand-written module
(`static/js/physics3d/scene-core.js`) so nothing depends on bare-specifier
sub-imports.

### To update

```powershell
Invoke-WebRequest -Uri "https://cdn.jsdelivr.net/npm/three@<version>/build/three.module.min.js" `
  -OutFile "static/js/vendor/three-<version>.module.min.js"
```

Then update the filename in the import map in `templates/physics/kinematics.html`
and `templates/physics/_physics3d_home.html` (if present), update this file, and
run the test suite.

## react-18.3.1.production.min.js / react-dom-18.3.1.production.min.js

- **Library:** React / ReactDOM
- **Version:** 18.3.1
- **Format:** classic UMD global scripts (`<script src>`, not an ES module or
  the import map) -- they define `window.React` / `window.ReactDOM`. Loaded
  with two plain `<script>` tags, in that order, before each React island's
  own bundle (`static/react/*.js`, built by `frontend/`; see
  `docs/REACT_ISLANDS.md`).
- **License:** MIT (`@license React`, header retained in each file)
- **Source:** https://unpkg.com/react@18.3.1/umd/react.production.min.js and
  https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js
- **SHA-256:** `D949F1C3687AEDADCEDAC85261865F29B17CD273997E7F6B2BFC53B2F9D4C4DD` (react),
  `35F4F974F4B2BCD44DA73963347F8952E341F83909E4498227D4E26B98F66F0D` (react-dom)

No JSX, no build tooling loaded at runtime -- `frontend/` compiles each
island's JSX to plain JS ahead of time with Vite; the browser only ever sees
these two vendored globals plus one compiled bundle per page.

### To update

```powershell
Invoke-WebRequest -Uri "https://unpkg.com/react@<version>/umd/react.production.min.js" `
  -OutFile "static/js/vendor/react-<version>.production.min.js"
Invoke-WebRequest -Uri "https://unpkg.com/react-dom@<version>/umd/react-dom.production.min.js" `
  -OutFile "static/js/vendor/react-dom-<version>.production.min.js"
```

Then update the filenames in every template that loads them, `frontend/package.json`'s
react/react-dom versions (so the compiled bundles match the vendored runtime),
this file, and run the test suite.
