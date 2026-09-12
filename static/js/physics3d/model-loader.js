/**
 * Loads a small, hand-rolled JSON mesh format into a THREE.BufferGeometry.
 *
 * This is deliberately NOT a glTF/OBJ loader: static/js/vendor/README.md
 * already documents this project's choice not to vendor Three.js's
 * `examples/jsm` add-ons (GLTFLoader included) so nothing depends on bare-
 * specifier sub-imports or a third-party binary/JSON parser. A "model" here
 * is just a flat, fully-validated JSON document -- positions, optional
 * normals, and a triangle index list -- fetched from a same-origin static
 * URL. There is no eval, no Function, and no code of any kind in the file;
 * see docs/BLENDER_WORKFLOW.md for how to produce one from Blender.
 *
 * Callers MUST treat a failed/rejected load as "keep the current geometry" --
 * every renderer that uses this starts with a plain THREE primitive so a
 * missing or malformed model file never blanks the scene.
 */

const DEFAULT_LIMITS = { maxVertices: 20000, maxTriangles: 20000 };

function isFiniteNumberArray(value) {
  if (!Array.isArray(value)) return false;
  for (let i = 0; i < value.length; i++) {
    if (typeof value[i] !== "number" || !isFinite(value[i])) return false;
  }
  return true;
}

/**
 * Fetches and validates the JSON at `url`, returning a THREE.BufferGeometry.
 * Rejects (never throws synchronously) on any network, shape or range
 * problem so callers can `.catch()` and fall back to their existing mesh.
 */
export function loadModelGeometry(THREE, url, limits) {
  const cap = Object.assign({}, DEFAULT_LIMITS, limits || {});
  return fetch(url, { credentials: "same-origin" })
    .then(function (res) {
      if (!res.ok) throw new Error("model fetch failed: " + res.status);
      return res.json();
    })
    .then(function (data) {
      if (!data || typeof data !== "object") throw new Error("model is not an object");
      const positions = data.positions;
      const indices = data.indices;
      const normals = data.normals;

      if (!isFiniteNumberArray(positions) || positions.length === 0 || positions.length % 3 !== 0) {
        throw new Error("invalid positions array");
      }
      if (!Array.isArray(indices) || indices.length === 0 || indices.length % 3 !== 0) {
        throw new Error("invalid indices array");
      }

      const vertexCount = positions.length / 3;
      const triangleCount = indices.length / 3;
      if (vertexCount > cap.maxVertices) throw new Error("model exceeds vertex limit");
      if (triangleCount > cap.maxTriangles) throw new Error("model exceeds triangle limit");

      for (let i = 0; i < indices.length; i++) {
        const idx = indices[i];
        if (!Number.isInteger(idx) || idx < 0 || idx >= vertexCount) {
          throw new Error("index out of range");
        }
      }

      const hasNormals = normals !== undefined;
      if (hasNormals && (!isFiniteNumberArray(normals) || normals.length !== positions.length)) {
        throw new Error("invalid normals array");
      }

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      geometry.setIndex(indices);
      if (hasNormals) {
        geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
      } else {
        geometry.computeVertexNormals();
      }
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
      return geometry;
    });
}
