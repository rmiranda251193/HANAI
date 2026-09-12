# Authoring a 3D model in Blender for the Physics Lab

The Kinematics 3D view (`static/js/physics3d/kinematics-3d.js`) draws its cart
from `static/models/cart.json` -- a small, hand-rolled JSON mesh format, not
glTF/OBJ. `static/js/vendor/README.md` already documents this project's
choice not to vendor Three.js's `examples/jsm` add-ons (which is where
`GLTFLoader` lives), to avoid a large third-party parser and its own
bare-specifier sub-imports. `static/js/physics3d/model-loader.js` is a ~70
line, fully-validated loader for this project's own flat format instead.

This means integrating a model you built in Blender is a two-step, no-install
process: model it, then run a short Python script *inside Blender's own
Scripting tab* (no add-on, no export plugin) to write the JSON file this app
already knows how to load.

## 1. Model it

- Work in metres -- 1 Blender unit = 1 metre, matching the scene scale.
- The current cart occupies a 1.6 m (x) x 1.1 m (y) x 2.0 m (z) box, centred
  on x and z, sitting on the track at y=0 (its origin is at half its height,
  y=0.55, set in code). Model within roughly that footprint so it doesn't
  clip the track, arrows or labels.
- Before exporting: **Object > Apply > All Transforms**, so the mesh's local
  coordinates are its final coordinates -- the exporter below does not apply
  the object's transform for you.
- Keep it low-poly (a few hundred triangles is plenty for a small on-screen
  cart); `model-loader.js` rejects anything over 20,000 vertices/triangles.
- Blender is Z-up; this app (like Three.js) is Y-up. The script below
  converts for you -- you don't need to rotate the model in Blender.

## 2. Export with a script, not an add-on

Open Blender's **Scripting** tab, select your object in the viewport so it is
`bpy.context.active_object`, paste this into a new text block, and run it
(Alt+P):

```python
import bpy, json

obj = bpy.context.active_object
mesh = obj.data
mesh.calc_loop_triangles()

positions = []
indices = []
seen = {}

for tri in mesh.loop_triangles:
    for vi in tri.vertices:
        co = mesh.vertices[vi].co
        key = (round(co.x, 6), round(co.y, 6), round(co.z, 6))
        if key not in seen:
            seen[key] = len(positions) // 3
            # Blender is Z-up; this app is Y-up.
            positions.extend([co.x, co.z, -co.y])
        indices.append(seen[key])

with open(bpy.path.abspath("//model.json"), "w") as f:
    json.dump({"positions": positions, "indices": indices}, f)

print("wrote", len(positions) // 3, "vertices,", len(indices) // 3, "triangles")
```

This writes `model.json` next to the saved `.blend` file. Normals are left
out deliberately -- `model-loader.js` calls `computeVertexNormals()` when
they're missing, which is simpler and more robust across Blender versions
than exporting split normals. If you want sharp (non-smoothed) edges, add a
Bevel or Edge Split modifier and apply it before running the script, or mark
sharp edges and extend the script to key vertices by `(position, normal)`
instead of position alone.

This script has not been run against a live Blender install in this
environment (none is available here) -- treat it as a verified-by-reading
starting point and sanity-check the printed vertex/triangle counts, and the
rendered shape, before relying on it.

## 3. Drop it in

Copy the exported file to `static/models/<name>.json`, point the template at
it (see `data-cart-model` on `[data-physics3d]` in
`templates/physics/kinematics.html`, resolved through `{% static %}` so it
still works with hashed filenames in production), and run the test suite.
The existing box mesh remains the fallback if the file is ever missing or
fails validation, so this is a safe, incremental swap.

## The JSON format

```json
{
  "positions": [x0, y0, z0, x1, y1, z1, ...],
  "indices":   [i0, i1, i2, ...],
  "normals":   [nx0, ny0, nz0, ...]
}
```

- `positions`: flat array of vertex coordinates, length a multiple of 3.
- `indices`: flat array of triangle vertex indices, length a multiple of 3,
  every value a valid index into `positions`.
- `normals` (optional): one normal per vertex, same length as `positions`.
  Omit it and the loader computes smooth vertex normals for you.

Nothing else is read from the file, and it is never executed -- it's parsed
with `Response.json()` and validated field-by-field before becoming a
`THREE.BufferGeometry`.
