/**
 * Home page decorative motif -- a slow, restrained wireframe "scientific
 * instrument" behind the hero text. Purely cosmetic:
 *
 *  - never blocks or conveys information (aria-hidden, pointer-events: none)
 *  - does nothing when WebGL is unavailable or reduced motion is requested
 *  - pauses when the tab is hidden and disposes on page unload
 *
 * The home page is fully usable with this file absent, blocked, or failing.
 */

import * as THREE from "three";
import { isWebGLAvailable, prefersReducedMotion } from "./webgl.js";

function boot() {
  const canvas = document.querySelector("[data-home-motif]");
  if (!canvas) return;
  if (prefersReducedMotion() || !isWebGLAvailable()) return;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "low-power",
    });
  } catch (err) {
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0, 9);

  const group = new THREE.Group();
  scene.add(group);

  // Colors tuned for the light workspace background (Section 5 of the
  // light-scientific-UI brief): a pale wireframe that popped on the old
  // dark theme all but disappears on a light backdrop, so this uses the
  // same deep "electric physics blue" as --cyan / a warm --amber core.
  const shellGeom = new THREE.IcosahedronGeometry(3, 1);
  const shellMat = new THREE.MeshBasicMaterial({
    color: 0x1261ff,
    wireframe: true,
    transparent: true,
    opacity: 0.35,
  });
  const shell = new THREE.Mesh(shellGeom, shellMat);
  group.add(shell);

  const coreGeom = new THREE.SphereGeometry(0.5, 16, 16);
  const coreMat = new THREE.MeshBasicMaterial({ color: 0xc9740f, transparent: true, opacity: 0.55 });
  const orb = new THREE.Mesh(coreGeom, coreMat);
  group.add(orb);

  function resize() {
    const w = canvas.clientWidth || 480;
    const h = canvas.clientHeight || 480;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  let rafId = null;
  let running = false;
  let t = 0;

  function frame() {
    if (!running) return;
    t += 0.004;
    group.rotation.y = t;
    group.rotation.x = Math.sin(t * 0.6) * 0.25;
    orb.position.set(Math.cos(t * 1.7) * 3, Math.sin(t * 1.3) * 3, Math.sin(t * 1.9) * 1.5);
    renderer.render(scene, camera);
    rafId = window.requestAnimationFrame(frame);
  }
  function start() {
    if (running) return;
    running = true;
    rafId = window.requestAnimationFrame(frame);
  }
  function stop() {
    running = false;
    if (rafId != null) window.cancelAnimationFrame(rafId);
    rafId = null;
  }
  function onVisibility() {
    if (document.hidden) stop();
    else start();
  }
  document.addEventListener("visibilitychange", onVisibility);

  function dispose() {
    stop();
    window.removeEventListener("resize", resize);
    document.removeEventListener("visibilitychange", onVisibility);
    shellGeom.dispose();
    shellMat.dispose();
    coreGeom.dispose();
    coreMat.dispose();
    renderer.dispose();
    if (renderer.forceContextLoss) {
      try { renderer.forceContextLoss(); } catch (err) { /* ignore */ }
    }
  }
  window.addEventListener("pagehide", dispose);

  start();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
