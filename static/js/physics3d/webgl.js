/**
 * WebGL capability check.
 *
 * Used to decide whether a 3D view can be offered at all. On failure the caller
 * keeps the existing 2D view -- the 3D layer is purely additive and its absence
 * must never break the experiment or its evidence.
 */

export function isWebGLAvailable() {
  try {
    if (typeof window === "undefined" || !window.WebGLRenderingContext) return false;
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl");
    return !!gl && typeof gl.getParameter === "function";
  } catch (err) {
    return false;
  }
}

export function prefersReducedMotion() {
  try {
    return (
      !!window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  } catch (err) {
    return false;
  }
}
