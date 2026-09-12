import React from "react";
import ReactDOM from "react-dom";

/**
 * Reads the JSON the server embedded in `data-state` on the mount element.
 * Returns `null` on anything unexpected -- a missing attribute or bad JSON
 * -- so a caller can bail out and leave the server-rendered fallback alone.
 */
export function readState(rootEl) {
  const raw = rootEl.getAttribute("data-state");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (err) {
    return null;
  }
}

/**
 * Mounts `App` into the element with id `rootId`, but ONLY if the element
 * exists and its bootstrap JSON parses. Every failure mode here (missing
 * root, bad JSON, the render itself throwing) is swallowed rather than
 * surfaced: every one of these pages has a complete, working
 * server-rendered fallback, and it must never be left blank because this
 * script errored. This is the same philosophy as the existing WebGL
 * fallback for the 3D Physics view (see static/js/physics3d/kinematics-3d.js).
 */
export function mountIsland(rootId, App) {
  const rootEl = document.getElementById(rootId);
  if (!rootEl) return;
  const state = readState(rootEl);
  if (state === null) return;
  try {
    const root = ReactDOM.createRoot(rootEl);
    root.render(React.createElement(App, { initialState: state, rootEl: rootEl }));
  } catch (err) {
    if (window.console && console.debug) {
      console.debug("[HANAI] React island failed to mount:", err);
    }
  }
}
