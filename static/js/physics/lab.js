/**
 * Physics Lab shell.
 *
 * Reusable, framework-free scaffolding shared by every simulation:
 *  - a registry mapping `data-simulation-type` to a factory
 *  - a run loop that respects `prefers-reduced-motion`
 *  - auto-mounting of every `.lab[data-simulation-type]` on the page
 *
 * Individual simulations (e.g. newtons-second-law.js) register a factory and
 * own their own physics, SVG and controls. This file contains no physics.
 */
(function (window, document) {
  "use strict";

  var registry = {};

  var prefersReducedMotion = false;
  try {
    prefersReducedMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (err) {
    prefersReducedMotion = false;
  }

  /**
   * A run loop that calls `onTick(dtSeconds)` repeatedly while running.
   * Smooth (requestAnimationFrame) normally; coarse discrete steps when the
   * viewer asked for reduced motion, so the numbers still advance.
   */
  function createRunLoop(onTick, options) {
    options = options || {};
    var reduced = prefersReducedMotion;
    var maxDt = options.maxDt || 0.05; // clamp big frame gaps (tab switches)
    var coarseDt = options.coarseDt || 0.2;
    var coarseIntervalMs = options.coarseIntervalMs || 200;
    var rafId = null;
    var timerId = null;
    var lastTs = 0;
    var running = false;

    function frame(ts) {
      if (!running) return;
      if (!lastTs) lastTs = ts;
      var dt = (ts - lastTs) / 1000;
      lastTs = ts;
      if (dt > maxDt) dt = maxDt;
      if (dt > 0) onTick(dt);
      rafId = window.requestAnimationFrame(frame);
    }

    return {
      reduced: reduced,
      isRunning: function () {
        return running;
      },
      start: function () {
        if (running) return;
        running = true;
        if (reduced || !window.requestAnimationFrame) {
          timerId = window.setInterval(function () {
            if (running) onTick(coarseDt);
          }, coarseIntervalMs);
        } else {
          lastTs = 0;
          rafId = window.requestAnimationFrame(frame);
        }
      },
      stop: function () {
        running = false;
        if (rafId && window.cancelAnimationFrame) {
          window.cancelAnimationFrame(rafId);
        }
        rafId = null;
        if (timerId) {
          window.clearInterval(timerId);
          timerId = null;
        }
        lastTs = 0;
      }
    };
  }

  function readNumber(el, name, fallback) {
    var raw = el.getAttribute("data-" + name);
    var value = parseFloat(raw);
    return isFinite(value) ? value : fallback;
  }

  var PhysicsLab = {
    prefersReducedMotion: prefersReducedMotion,
    createRunLoop: createRunLoop,

    register: function (type, factory) {
      registry[type] = factory;
    },

    mount: function (root) {
      if (!root || root.getAttribute("data-lab-mounted") === "true") return null;
      var type = root.getAttribute("data-simulation-type");
      var factory = registry[type];
      if (typeof factory !== "function") return null;
      var config = {
        mass: readNumber(root, "mass", 1),
        force: readNumber(root, "force", 0),
        massMin: readNumber(root, "mass-min", 0.1),
        massMax: readNumber(root, "mass-max", 20),
        forceMin: readNumber(root, "force-min", 0),
        forceMax: readNumber(root, "force-max", 50),
        tutorBase: root.getAttribute("data-tutor-base") || ""
      };
      var instance = factory(root, config, PhysicsLab);
      root.setAttribute("data-lab-mounted", "true");
      return instance;
    },

    mountAll: function () {
      var nodes = document.querySelectorAll(".lab[data-simulation-type]");
      var instances = [];
      for (var i = 0; i < nodes.length; i++) {
        var instance = PhysicsLab.mount(nodes[i]);
        if (instance) instances.push(instance);
      }
      return instances;
    }
  };

  window.PhysicsLab = PhysicsLab;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      PhysicsLab.mountAll();
    });
  } else {
    PhysicsLab.mountAll();
  }
})(window, document);
