/**
 * Generic, topic-agnostic Three.js scaffold for HANAI Physics visualizations.
 *
 * This module knows nothing about kinematics, forces, or any simulation type.
 * It provides a renderer, a camera with keyboard-accessible orbit/zoom/pan, a
 * grid, helpers for arrows and text labels, a bounded animation loop, and
 * thorough disposal. It never computes Physics -- callers pass in already
 * computed, server-authoritative state and this module only draws it.
 *
 * Topic-specific scenes live in their own module (e.g. kinematics-3d.js) and
 * are the only place a `simulationType === "..."` decision is allowed.
 */

import * as THREE from "three";

const MAX_PIXEL_RATIO = 2;

/**
 * Minimal, dependency-free orbit controller.
 * - pointer drag: rotate    - wheel: zoom    - shift/2-finger drag: pan
 * - keyboard (when focused): arrows rotate, +/- zoom, 0 or r resets
 */
function createOrbit(camera, domElement, target, reducedMotion) {
  const state = {
    radius: camera.position.distanceTo(target),
    theta: Math.atan2(camera.position.x - target.x, camera.position.z - target.z),
    phi: Math.acos(
      Math.min(1, Math.max(-1, (camera.position.y - target.y) / Math.max(1e-6, camera.position.distanceTo(target))))
    ),
  };
  const home = { ...state, target: target.clone() };
  const MIN_PHI = 0.15;
  const MAX_PHI = Math.PI - 0.15;
  const MIN_R = 4;
  const MAX_R = 220;
  let dragging = false;
  let panning = false;
  let lastX = 0;
  let lastY = 0;
  let dirty = true;

  function apply() {
    const sinPhi = Math.sin(state.phi);
    camera.position.set(
      target.x + state.radius * sinPhi * Math.sin(state.theta),
      target.y + state.radius * Math.cos(state.phi),
      target.z + state.radius * sinPhi * Math.cos(state.theta)
    );
    camera.lookAt(target);
    dirty = false;
  }

  function rotate(dx, dy) {
    state.theta -= dx * 0.005;
    state.phi = Math.min(MAX_PHI, Math.max(MIN_PHI, state.phi - dy * 0.005));
    dirty = true;
  }
  function zoom(amount) {
    state.radius = Math.min(MAX_R, Math.max(MIN_R, state.radius * (1 + amount)));
    dirty = true;
  }
  function pan(dx, dy) {
    const panScale = state.radius * 0.0015;
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
    target.addScaledVector(right, -dx * panScale);
    target.addScaledVector(up, dy * panScale);
    dirty = true;
  }

  function onPointerDown(e) {
    dragging = true;
    panning = e.shiftKey || e.button === 2 || e.button === 1;
    lastX = e.clientX;
    lastY = e.clientY;
    domElement.setPointerCapture && domElement.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    if (panning) pan(dx, dy);
    else rotate(dx, dy);
  }
  function onPointerUp(e) {
    dragging = false;
    panning = false;
    domElement.releasePointerCapture && e.pointerId != null &&
      domElement.releasePointerCapture(e.pointerId);
  }
  function onWheel(e) {
    e.preventDefault();
    zoom(e.deltaY > 0 ? 0.1 : -0.1);
  }
  function onKeyDown(e) {
    const step = 26;
    switch (e.key) {
      case "ArrowLeft": rotate(-step, 0); break;
      case "ArrowRight": rotate(step, 0); break;
      case "ArrowUp": rotate(0, -step); break;
      case "ArrowDown": rotate(0, step); break;
      case "+": case "=": zoom(-0.12); break;
      case "-": case "_": zoom(0.12); break;
      case "0": case "r": case "R": case "Home": reset(); break;
      default: return;
    }
    e.preventDefault();
  }
  function onContextMenu(e) { e.preventDefault(); }

  function reset() {
    state.radius = home.radius;
    state.theta = home.theta;
    state.phi = home.phi;
    target.copy(home.target);
    dirty = true;
  }

  domElement.addEventListener("pointerdown", onPointerDown);
  domElement.addEventListener("pointermove", onPointerMove);
  domElement.addEventListener("pointerup", onPointerUp);
  domElement.addEventListener("pointercancel", onPointerUp);
  domElement.addEventListener("wheel", onWheel, { passive: false });
  domElement.addEventListener("keydown", onKeyDown);
  domElement.addEventListener("contextmenu", onContextMenu);

  apply();

  return {
    update() {
      if (dirty) apply();
      return dirty;
    },
    needsRender() { return dirty; },
    reset,
    dispose() {
      domElement.removeEventListener("pointerdown", onPointerDown);
      domElement.removeEventListener("pointermove", onPointerMove);
      domElement.removeEventListener("pointerup", onPointerUp);
      domElement.removeEventListener("pointercancel", onPointerUp);
      domElement.removeEventListener("wheel", onWheel);
      domElement.removeEventListener("keydown", onKeyDown);
      domElement.removeEventListener("contextmenu", onContextMenu);
    },
    // reducedMotion is honoured by callers (no idle camera drift); kept for API symmetry.
    reducedMotion: !!reducedMotion,
  };
}

function makeLabelTexture(text) {
  const pad = 12;
  const font = "600 30px Inter, system-ui, sans-serif";
  const measure = document.createElement("canvas").getContext("2d");
  measure.font = font;
  const w = Math.ceil(measure.measureText(text).width) + pad * 2;
  const h = 48;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.font = font;
  ctx.fillStyle = "rgba(9, 18, 29, 0.9)";
  ctx.strokeStyle = "rgba(172, 215, 232, 0.5)";
  ctx.lineWidth = 2;
  roundRect(ctx, 1, 1, w - 2, h - 2, 8);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#edf6fb";
  ctx.textBaseline = "middle";
  ctx.fillText(text, pad, h / 2 + 1);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return { texture, aspect: w / h };
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function createSceneCore(canvas, options) {
  options = options || {};
  const reducedMotion = !!options.reducedMotion;

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: !reducedMotion,
    alpha: true,
    powerPreference: "low-power",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO));
  if ("outputColorSpace" in renderer) renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const target = new THREE.Vector3(
    options.target ? options.target.x : 0,
    options.target ? options.target.y : 0,
    options.target ? options.target.z : 0
  );

  const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000);
  const start = options.cameraStart || { x: 14, y: 12, z: 22 };
  camera.position.set(start.x, start.y, start.z);
  camera.lookAt(target);

  scene.add(new THREE.AmbientLight(0xbfe6f2, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 0.6);
  key.position.set(8, 18, 12);
  scene.add(key);

  const grid = new THREE.GridHelper(
    options.gridSize || 60,
    options.gridDivisions || 60,
    0x3a6070,
    0x22333d
  );
  grid.material.transparent = true;
  grid.material.opacity = 0.5;
  scene.add(grid);

  const content = new THREE.Group();
  scene.add(content);

  const orbit = createOrbit(canvas, camera, target, reducedMotion);

  let rafId = null;
  let running = false;
  let disposed = false;
  const labels = [];

  function render() {
    if (disposed) return;
    renderer.render(scene, camera);
  }

  function frame() {
    if (!running || disposed) return;
    orbit.update();
    render();
    rafId = window.requestAnimationFrame(frame);
  }

  function startLoop() {
    if (running || disposed) return;
    running = true;
    rafId = window.requestAnimationFrame(frame);
  }
  function stopLoop() {
    running = false;
    if (rafId != null && window.cancelAnimationFrame) window.cancelAnimationFrame(rafId);
    rafId = null;
  }

  function resize() {
    if (disposed) return;
    const w = canvas.clientWidth || 640;
    const h = canvas.clientHeight || 360;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    render();
  }

  let resizeObserver = null;
  try {
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(function () { resize(); });
      resizeObserver.observe(canvas);
    } else {
      window.addEventListener("resize", resize);
    }
  } catch (err) {
    window.addEventListener("resize", resize);
  }
  resize();

  function addArrow(color) {
    const arrow = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(0, 0, 0),
      1,
      color,
      0.9,
      0.5
    );
    content.add(arrow);
    return arrow;
  }

  function setArrow(arrow, origin, dir, length) {
    if (length <= 0 || !isFinite(length)) {
      arrow.visible = false;
      return;
    }
    arrow.visible = true;
    arrow.position.copy(origin);
    arrow.setDirection(dir.clone().normalize());
    arrow.setLength(length, Math.min(0.9, length * 0.28), Math.min(0.5, length * 0.16));
  }

  function addLabel(text) {
    const { texture, aspect } = makeLabelTexture(text);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(material);
    const scale = 2.4;
    sprite.scale.set(scale * aspect, scale, 1);
    sprite.userData.text = text;
    content.add(sprite);
    labels.push(sprite);
    return sprite;
  }

  function updateLabel(sprite, text) {
    if (sprite.userData.text === text) return;
    sprite.userData.text = text;
    const { texture, aspect } = makeLabelTexture(text);
    if (sprite.material.map) sprite.material.map.dispose();
    sprite.material.map = texture;
    sprite.material.needsUpdate = true;
    const scale = 2.4;
    sprite.scale.set(scale * aspect, scale, 1);
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    stopLoop();
    if (resizeObserver) resizeObserver.disconnect();
    else window.removeEventListener("resize", resize);
    orbit.dispose();
    scene.traverse(function (obj) {
      if (obj.geometry) obj.geometry.dispose();
      const mats = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : [];
      mats.forEach(function (m) {
        if (m.map) m.map.dispose();
        m.dispose();
      });
    });
    renderer.dispose();
    if (renderer.forceContextLoss) {
      try { renderer.forceContextLoss(); } catch (err) { /* ignore */ }
    }
  }

  return {
    THREE,
    scene,
    camera,
    renderer,
    content,
    orbit,
    reducedMotion,
    render,
    startLoop,
    stopLoop,
    resize,
    addArrow,
    setArrow,
    addLabel,
    updateLabel,
    resetCamera: orbit.reset,
    isDisposed() { return disposed; },
    dispose,
  };
}
