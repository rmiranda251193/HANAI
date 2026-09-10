/**
 * Kinematics 3D view -- the ONLY simulation-specific 3D module, plus the small
 * bootstrap that wires the 2D/3D toggle on the Physics Lab kinematics page.
 *
 * It computes no Physics. It listens to the `lab:state` CustomEvent that
 * static/js/physics/kinematics.js already dispatches (initial conditions and
 * the position/velocity it computed for the current time, using the same
 * formulas as apps/physics/simulations_kinematics.py, re-validated on the
 * server at submit time) and draws that state: a cart on a straight track with
 * labelled position, velocity and acceleration, plus vectors.
 *
 * Renderer selection is an allow-list lookup on a data attribute -- never a URL,
 * never eval, never a dynamic import path built from page data.
 */

import * as THREE from "three";
import { createSceneCore } from "./scene-core.js";
import { isWebGLAvailable, prefersReducedMotion } from "./webgl.js";

const VELOCITY_COLOR = 0x55d7eb; // cyan  -- also labelled "v"
const ACCEL_COLOR = 0xf2b466; // amber -- also labelled "a"
const CART_COLOR = 0x9fd8e6;
const TRACK_COLOR = 0x1b2b38;

const MAX_ABS_V = 20; // matches simulations_kinematics.py bounds
const MAX_ABS_A = 10;
const ARROW_MAX_LEN = 9;
const ARROW_MIN_LEN = 0.7;

function fmt(n, digits) {
  return Number(n).toFixed(digits == null ? 2 : digits);
}

/** Honest per-type scaling: proportional within [MIN, MAX], never exaggerated. */
function arrowLength(value, maxAbs) {
  const mag = Math.abs(Number(value) || 0);
  if (mag < 1e-3) return 0;
  const scaled = (mag / maxAbs) * ARROW_MAX_LEN;
  return Math.max(ARROW_MIN_LEN, Math.min(ARROW_MAX_LEN, scaled));
}

function buildKinematicsScene(core) {
  const THREE_ = core.THREE;

  // Straight track along X (1 world unit == 1 metre).
  const track = new THREE_.Mesh(
    new THREE_.BoxGeometry(44, 0.3, 3),
    new THREE_.MeshStandardMaterial({ color: TRACK_COLOR, roughness: 0.9, metalness: 0 })
  );
  track.position.y = -0.15;
  core.content.add(track);

  // Bright X axis with metre ticks + numeric labels (measurement, not colour alone).
  const axisMat = new THREE_.LineBasicMaterial({ color: 0x8fd6e6 });
  const axisGeom = new THREE_.BufferGeometry().setFromPoints([
    new THREE_.Vector3(-21, 0.02, 0),
    new THREE_.Vector3(21, 0.02, 0),
  ]);
  core.content.add(new THREE_.Line(axisGeom, axisMat));
  const tickLabels = [];
  for (let m = -20; m <= 20; m += 5) {
    const tick = new THREE_.Line(
      new THREE_.BufferGeometry().setFromPoints([
        new THREE_.Vector3(m, 0.02, -0.6),
        new THREE_.Vector3(m, 0.02, 0.6),
      ]),
      axisMat
    );
    core.content.add(tick);
    const label = core.addLabel(m + " m");
    label.position.set(m, 0.9, -1.9);
    label.scale.multiplyScalar(0.55);
    tickLabels.push(label);
  }

  const cart = new THREE_.Mesh(
    new THREE_.BoxGeometry(1.6, 1.1, 2),
    new THREE_.MeshStandardMaterial({ color: CART_COLOR, roughness: 0.5, metalness: 0.1 })
  );
  cart.position.y = 0.55;
  core.content.add(cart);

  const marker = new THREE_.Mesh(
    new THREE_.ConeGeometry(0.35, 0.7, 16),
    new THREE_.MeshStandardMaterial({ color: 0xedf6fb })
  );
  marker.rotation.x = Math.PI;
  marker.position.y = 1.7;
  core.content.add(marker);

  const vArrow = core.addArrow(VELOCITY_COLOR);
  const aArrow = core.addArrow(ACCEL_COLOR);

  // Motion trail -- markers at authoritative sampled positions (see lab-instrument.js).
  const trailGroup = new THREE_.Group();
  core.content.add(trailGroup);
  const trailGeom = new THREE_.SphereGeometry(0.22, 10, 10);
  const trailMat = new THREE_.MeshBasicMaterial({ color: 0x8fd6e6, transparent: true, opacity: 0.7 });
  function setTrail(points) {
    while (trailGroup.children.length) trailGroup.remove(trailGroup.children[0]);
    (points || []).forEach(function (px) {
      const dot = new THREE_.Mesh(trailGeom, trailMat);
      dot.position.set(Math.max(-21, Math.min(21, Number(px) || 0)), 0.25, 0);
      trailGroup.add(dot);
    });
    core.render();
  }

  const valueLabels = {
    t: core.addLabel("t = 0.0 s"),
    x: core.addLabel("x = 0.00 m"),
    v: core.addLabel("v = 0.00 m/s"),
    a: core.addLabel("a = 0.00 m/s²"),
  };

  function update(state) {
    const x = Number(state.positionM) || 0;
    const v = Number(state.velocityMs) || 0;
    const a = Number(state.accelerationMs2) || 0;
    const t = Number(state.timeS) || 0;

    // Keep the cart visible even if x exceeds the drawn track.
    const worldX = Math.max(-21, Math.min(21, x));
    cart.position.x = worldX;
    marker.position.x = worldX;

    const vDir = new THREE_.Vector3(v >= 0 ? 1 : -1, 0, 0);
    const aDir = new THREE_.Vector3(a >= 0 ? 1 : -1, 0, 0);
    core.setArrow(vArrow, new THREE_.Vector3(worldX, 1.2, 0.4), vDir, arrowLength(v, MAX_ABS_V));
    core.setArrow(aArrow, new THREE_.Vector3(worldX, 1.2, -0.4), aDir, arrowLength(a, MAX_ABS_A));

    core.updateLabel(valueLabels.t, "t = " + fmt(t, 1) + " s");
    core.updateLabel(valueLabels.x, "x = " + fmt(x) + " m");
    core.updateLabel(valueLabels.v, "v = " + fmt(v) + " m/s");
    core.updateLabel(valueLabels.a, "a = " + fmt(a) + " m/s²");
    valueLabels.t.position.set(worldX, 4.4, 0);
    valueLabels.x.position.set(worldX, 3.6, 0);
    valueLabels.v.position.set(worldX + (v >= 0 ? 3.2 : -3.2), 1.9, 0.4);
    valueLabels.a.position.set(worldX + (a >= 0 ? 3.2 : -3.2), 0.6, -0.4);

    core.render();
  }

  return { update, setTrail };
}

const RENDERERS = { "kinematics-3d": buildKinematicsScene };

function announce(summaryEl, state) {
  if (!summaryEl) return;
  const v = Number(state.velocityMs) || 0;
  const a = Number(state.accelerationMs2) || 0;
  const dir = v > 0.001 ? "positive x direction" : v < -0.001 ? "negative x direction" : "at rest";
  summaryEl.textContent =
    "Physics visualization: a cart on a straight track. " +
    "Time " + fmt(state.timeS, 1) + " seconds. " +
    "Position " + fmt(state.positionM) + " metres. " +
    "Velocity " + fmt(v) + " metres per second (" + dir + "). " +
    "Acceleration " + fmt(a) + " metres per second squared.";
}

function boot() {
  const mount = document.querySelector("[data-physics3d]");
  const root = document.querySelector(".lab.lab-flow");
  if (!mount || !root) return;

  const rendererSlug = mount.getAttribute("data-renderer") || "";
  const build = Object.prototype.hasOwnProperty.call(RENDERERS, rendererSlug)
    ? RENDERERS[rendererSlug]
    : null;

  const wrap2d = document.querySelector("[data-lab-scene-2d]");
  const wrap3d = document.querySelector("[data-physics3d-canvas-wrap]");
  const canvas = document.querySelector("[data-physics3d-canvas]");
  const fallback = document.querySelector("[data-physics3d-fallback]");
  const summary = document.querySelector("[data-physics3d-summary]");
  const cameraResetBtn = document.querySelector("[data-physics3d-camera-reset]");
  const toggles = Array.prototype.slice.call(
    document.querySelectorAll('[name="lab-view"]')
  );

  const webgl = build && isWebGLAvailable();

  function showFallback(message) {
    if (fallback) {
      fallback.textContent =
        message ||
        "The 3D view is not available on this device. The 2D Physics view below shows the same values.";
      fallback.hidden = false;
    }
    toggles.forEach(function (t) {
      if (t.value === "3d") {
        t.disabled = true;
        const label = t.closest("label");
        if (label) label.classList.add("is-disabled");
      }
    });
  }

  let core = null;
  let scene = null;
  let lastState = null;
  let active3d = false;

  function ensureScene() {
    if (core || !webgl) return;
    try {
      core = createSceneCore(canvas, {
        reducedMotion: prefersReducedMotion(),
        cameraStart: { x: 10, y: 11, z: 24 },
        target: { x: 0, y: 1, z: 0 },
        gridSize: 60,
        gridDivisions: 30,
      });
      scene = build(core);
      if (lastState) {
        scene.update(lastState);
        announce(summary, lastState);
      }
      if (lastTrail.length && scene.setTrail) scene.setTrail(lastTrail);
    } catch (err) {
      core = null;
      scene = null;
      showFallback();
      setView("2d");
    }
  }

  function setView(view) {
    active3d = view === "3d" && webgl;
    if (wrap2d) wrap2d.hidden = active3d;
    if (wrap3d) wrap3d.hidden = !active3d;
    if (active3d) {
      ensureScene();
      if (core) {
        core.resize();
        core.startLoop();
      }
    } else if (core) {
      core.stopLoop();
    }
    try { window.localStorage.setItem("hanai:labView", view); } catch (err) { /* ignore */ }
  }

  if (!webgl) {
    showFallback(
      build
        ? "This device or browser cannot show the 3D view (WebGL is unavailable). " +
            "The 2D Physics view below shows the same values."
        : null
    );
  }

  toggles.forEach(function (t) {
    t.addEventListener("change", function () {
      if (t.checked) setView(t.value);
    });
  });

  if (cameraResetBtn) {
    cameraResetBtn.addEventListener("click", function () {
      if (core) {
        core.resetCamera();
        core.render();
      }
    });
  }

  root.addEventListener("lab:state", function (e) {
    lastState = e.detail;
    if (active3d && scene) {
      scene.update(lastState);
      announce(summary, lastState);
    }
  });

  let lastTrail = [];
  root.addEventListener("lab:trail", function (e) {
    lastTrail = e.detail && e.detail.on ? (e.detail.points || []) : [];
    if (scene && scene.setTrail) scene.setTrail(lastTrail);
  });

  function onVisibility() {
    if (!core) return;
    if (document.hidden || !active3d) core.stopLoop();
    else core.startLoop();
  }
  document.addEventListener("visibilitychange", onVisibility);

  function teardown() {
    if (core) core.dispose();
    core = null;
    scene = null;
  }
  window.addEventListener("pagehide", teardown);
  window.addEventListener("beforeunload", teardown);

  // Restore the last chosen view (defaults to 2D).
  let initial = "2d";
  try {
    if (webgl && window.localStorage.getItem("hanai:labView") === "3d") initial = "3d";
  } catch (err) { /* ignore */ }
  const initialToggle = toggles.filter(function (t) { return t.value === initial; })[0];
  if (initialToggle) initialToggle.checked = true;
  setView(initial);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
