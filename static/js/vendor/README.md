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
