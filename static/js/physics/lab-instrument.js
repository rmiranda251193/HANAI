/**
 * Physics Lab -- scientific instrument layer.
 *
 * Presentation only. It listens to the `lab:state` CustomEvent that
 * kinematics.js already dispatches (server-mirrored values, re-validated on the
 * server at submit time) and drives: the live HUD, the state inspector, the
 * vector inspector, the motion trail (2D), the measurement tool, the
 * two-experiment comparison, the scenario-challenge checker, and the
 * "Challenge the AI" claim checker. It computes no authoritative Physics --
 * comparison/measurement use the same exported `PhysicsLab.Kinematics.computeState`
 * that mirrors the Python model, and both the scenario check and the claim's
 * ground truth are answered by the server, never guessed client-side.
 */
(function (window, document) {
  "use strict";

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function fmt(n, d) {
    return Number(n).toFixed(d == null ? 2 : d);
  }
  function q(root, sel) {
    return root.querySelector(sel);
  }
  function qa(root, sel) {
    return Array.prototype.slice.call(root.querySelectorAll(sel));
  }

  function motionDescription(v, a) {
    if (Math.abs(v) < 0.05 && Math.abs(a) < 0.05) return "At rest.";
    var dir = v > 0.05 ? "in the +x direction" : v < -0.05 ? "in the -x direction" : "momentarily at rest";
    if (Math.abs(a) < 0.05) return "Moving at constant velocity " + dir + ".";
    var sameSign = v * a > 0;
    if (Math.abs(v) < 0.05) return "Speeding up from rest " + (a > 0 ? "in the +x direction." : "in the -x direction.");
    return (sameSign ? "Speeding up " : "Slowing down ") + dir + ".";
  }

  ready(function () {
    var root = q(document, ".lab.lab-flow");
    if (!root) return;
    var instrument = q(document, "[data-lab-instrument]");
    if (!instrument) return;

    var last = null;

    // --- HUD + state inspector + vector inspector -----------------
    var hud = {
      time: q(instrument, "[data-hud-time]"),
      x: q(instrument, "[data-hud-position]"),
      v: q(instrument, "[data-hud-velocity]"),
      a: q(instrument, "[data-hud-acceleration]"),
      motion: q(instrument, "[data-hud-motion]"),
      summary: q(instrument, "[data-hud-summary]")
    };
    var inspect = {
      x0: q(instrument, "[data-inspect-x0]"),
      v0: q(instrument, "[data-inspect-v0]"),
      a0: q(instrument, "[data-inspect-a]"),
      t: q(instrument, "[data-inspect-t]"),
      x: q(instrument, "[data-inspect-x]"),
      v: q(instrument, "[data-inspect-v]")
    };
    var vec = {
      inputs: qa(instrument, "[name='lab-vector']"),
      magnitude: q(instrument, "[data-vec-magnitude]"),
      direction: q(instrument, "[data-vec-direction]"),
      meaning: q(instrument, "[data-vec-meaning]")
    };

    function renderVector() {
      if (!last || !vec.magnitude) return;
      var selected = vec.inputs.filter(function (i) { return i.checked; })[0];
      var which = selected ? selected.value : "velocity";
      var value = which === "acceleration" ? last.accelerationMs2 : last.velocityMs;
      vec.magnitude.textContent = fmt(Math.abs(value)) + (which === "acceleration" ? " m/s²" : " m/s");
      vec.direction.textContent = value > 0.001 ? "+x" : value < -0.001 ? "-x" : "zero";
      vec.meaning.textContent =
        which === "acceleration"
          ? "Acceleration is the rate of change of velocity. A non-zero value means the velocity is changing."
          : "Velocity is the rate of change of position. Its sign is the direction of motion.";
    }
    vec.inputs.forEach(function (i) { i.addEventListener("change", renderVector); });

    function onState(state) {
      last = state;
      if (hud.time) hud.time.textContent = fmt(state.timeS, 2);
      if (hud.x) hud.x.textContent = fmt(state.positionM);
      if (hud.v) hud.v.textContent = fmt(state.velocityMs);
      if (hud.a) hud.a.textContent = fmt(state.accelerationMs2);
      if (hud.motion) hud.motion.textContent = motionDescription(state.velocityMs, state.accelerationMs2);
      if (hud.summary) {
        hud.summary.textContent =
          "Current Physics state. Time " + fmt(state.timeS, 1) + " seconds. " +
          "Position " + fmt(state.positionM) + " metres. Velocity " + fmt(state.velocityMs) +
          " metres per second. Acceleration " + fmt(state.accelerationMs2) +
          " metres per second squared. " + motionDescription(state.velocityMs, state.accelerationMs2);
      }
      if (inspect.x0) inspect.x0.textContent = fmt(state.initialPositionM);
      if (inspect.v0) inspect.v0.textContent = fmt(state.initialVelocityMs);
      if (inspect.a0) inspect.a0.textContent = fmt(state.accelerationMs2);
      if (inspect.t) inspect.t.textContent = fmt(state.timeS, 2);
      if (inspect.x) inspect.x.textContent = fmt(state.positionM);
      if (inspect.v) inspect.v.textContent = fmt(state.velocityMs);
      renderVector();
      updateTrail(state);
    }

    // --- motion trail (2D SVG) ----------------------------------
    var trailGroup = q(root, "[data-lab-trail]");
    var trailBtn = q(instrument, "[data-action-trail-toggle]");
    var trailClearBtn = q(instrument, "[data-action-trail-clear]");
    var trailOn = false;
    var trailPts = [];

    function drawTrail() {
      if (!trailGroup) return;
      while (trailGroup.firstChild) trailGroup.removeChild(trailGroup.firstChild);
      if (!trailOn) return;
      var TRACK_CENTER = 320, PX_PER_M = 9;
      trailPts.forEach(function (x) {
        var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        c.setAttribute("cx", (TRACK_CENTER + x * PX_PER_M).toFixed(1));
        c.setAttribute("cy", "120");
        c.setAttribute("r", "3");
        c.setAttribute("class", "lab-trail-dot");
        trailGroup.appendChild(c);
      });
    }
    function updateTrail(state) {
      if (!trailOn) return;
      var x = state.positionM;
      if (!trailPts.length || Math.abs(x - trailPts[trailPts.length - 1]) >= 0.4) {
        trailPts.push(x);
        if (trailPts.length > 120) trailPts.shift();
        drawTrail();
      }
      root.dispatchEvent(new CustomEvent("lab:trail", { detail: { on: true, points: trailPts.slice() } }));
    }
    if (trailBtn) {
      trailBtn.addEventListener("click", function () {
        trailOn = !trailOn;
        trailBtn.setAttribute("aria-pressed", String(trailOn));
        trailBtn.textContent = trailOn ? "Hide trail" : "Show trail";
        if (!trailOn) trailPts = [];
        drawTrail();
        root.dispatchEvent(new CustomEvent("lab:trail", { detail: { on: trailOn, points: trailPts.slice() } }));
      });
    }
    if (trailClearBtn) {
      trailClearBtn.addEventListener("click", function () {
        trailPts = [];
        drawTrail();
        root.dispatchEvent(new CustomEvent("lab:trail", { detail: { on: trailOn, points: [] } }));
      });
    }

    // --- measurement tool ------------------------------------
    var measure = {
      x1: q(instrument, "[data-measure-x1]"),
      t1: q(instrument, "[data-measure-t1]"),
      x2: q(instrument, "[data-measure-x2]"),
      t2: q(instrument, "[data-measure-t2]"),
      cap1: q(instrument, "[data-measure-capture1]"),
      cap2: q(instrument, "[data-measure-capture2]"),
      dx: q(instrument, "[data-measure-dx]"),
      dt: q(instrument, "[data-measure-dt]"),
      reveal: q(instrument, "[data-measure-reveal]"),
      answer: q(instrument, "[data-measure-answer]")
    };
    function measureRefresh() {
      if (!measure.dx) return;
      var x1 = parseFloat(measure.x1.value), t1 = parseFloat(measure.t1.value);
      var x2 = parseFloat(measure.x2.value), t2 = parseFloat(measure.t2.value);
      var dx = x2 - x1, dt = t2 - t1;
      measure.dx.textContent = isFinite(dx) ? fmt(dx) + " m" : "--";
      measure.dt.textContent = isFinite(dt) ? fmt(dt) + " s" : "--";
      if (measure.answer) measure.answer.hidden = true;
    }
    ["x1", "t1", "x2", "t2"].forEach(function (k) {
      if (measure[k]) measure[k].addEventListener("input", measureRefresh);
    });
    if (measure.cap1) measure.cap1.addEventListener("click", function () {
      if (!last) return;
      measure.x1.value = fmt(last.positionM); measure.t1.value = fmt(last.timeS, 2); measureRefresh();
    });
    if (measure.cap2) measure.cap2.addEventListener("click", function () {
      if (!last) return;
      measure.x2.value = fmt(last.positionM); measure.t2.value = fmt(last.timeS, 2); measureRefresh();
    });
    if (measure.reveal && measure.answer) {
      measure.reveal.addEventListener("click", function () {
        var dx = parseFloat(measure.x2.value) - parseFloat(measure.x1.value);
        var dt = parseFloat(measure.t2.value) - parseFloat(measure.t1.value);
        if (!isFinite(dx) || !isFinite(dt) || dt === 0) {
          measure.answer.textContent = "Pick two different times first.";
        } else {
          measure.answer.textContent =
            "Average velocity = Δx / Δt = " + fmt(dx) + " / " + fmt(dt) +
            " = " + fmt(dx / dt) + " m/s. Compare this with the value you calculated.";
        }
        measure.answer.hidden = false;
      });
    }

    // --- two-experiment comparison -------------------------
    var K = window.PhysicsLab && window.PhysicsLab.Kinematics;
    var compare = {
      v0: q(instrument, "[data-compare-v0]"),
      a: q(instrument, "[data-compare-a]"),
      t: q(instrument, "[data-compare-t]"),
      run: q(instrument, "[data-compare-run]"),
      out: q(instrument, "[data-compare-out]")
    };
    if (compare.run && compare.out && K) {
      compare.run.addEventListener("click", function () {
        if (!last) return;
        var t = Math.max(0, Math.min(K.MAX_TIME_S, parseFloat(compare.t.value) || 5));
        var a = K.computeState(last.initialPositionM, last.initialVelocityMs, last.accelerationMs2, t);
        var b = K.computeState(
          last.initialPositionM,
          K.clampV0(parseFloat(compare.v0.value)),
          K.clampAccel(parseFloat(compare.a.value)),
          t
        );
        var faster = Math.abs(a.velocity) > Math.abs(b.velocity) ? "Experiment A" :
          Math.abs(b.velocity) > Math.abs(a.velocity) ? "Experiment B" : "neither (they are equal)";
        compare.out.textContent =
          "At t = " + fmt(t, 1) + " s -- A: velocity " + fmt(a.velocity) + " m/s, position " + fmt(a.position) +
          " m. B: velocity " + fmt(b.velocity) + " m/s, position " + fmt(b.position) + " m. " +
          "Greater speed: " + faster + ". In your explanation, say why.";
      });
    }

    // --- scenario challenge checker -----------------------
    var scenario = {
      select: q(instrument, "[data-scenario-select]"),
      desc: q(instrument, "[data-scenario-desc]"),
      goals: q(instrument, "[data-scenario-goals]"),
      check: q(instrument, "[data-scenario-check]"),
      result: q(instrument, "[data-scenario-result]")
    };
    var scenarioData = {};
    try {
      scenarioData = JSON.parse(instrument.getAttribute("data-scenarios") || "{}");
    } catch (e) { scenarioData = {}; }
    var checkBase = instrument.getAttribute("data-scenario-check-base") || "";

    function renderScenario() {
      if (!scenario.select) return;
      var s = scenarioData[scenario.select.value];
      if (!s) return;
      if (scenario.desc) scenario.desc.textContent = s.description;
      if (scenario.goals) {
        scenario.goals.textContent = "";
        (s.goals || []).forEach(function (g) {
          var li = document.createElement("li");
          li.textContent = g;
          scenario.goals.appendChild(li);
        });
      }
      if (scenario.result) scenario.result.textContent = "";
    }
    if (scenario.select) {
      scenario.select.addEventListener("change", renderScenario);
      // A lesson's "Open the Scenario" link may pre-select a specific
      // teacher-authored scenario (?scenario=<slug> on the page URL,
      // resolved and validated server-side into this data attribute) --
      // purely a display convenience, changes no Physics or evidence.
      var preselect = instrument.getAttribute("data-selected-scenario") || "";
      if (preselect && scenarioData[preselect]) {
        scenario.select.value = preselect;
        var scenarioDetails = scenario.select.closest("details");
        if (scenarioDetails) scenarioDetails.open = true;
      }
      renderScenario();
    }
    function csrfToken() {
      var el = q(root, "input[name=csrfmiddlewaretoken]");
      return el ? el.value : "";
    }
    if (scenario.check && scenario.result) {
      scenario.check.addEventListener("click", function () {
        if (!last || !scenario.select || !checkBase) return;
        var url = checkBase.replace("SCENARIO_ID", encodeURIComponent(scenario.select.value));
        var body = new FormData();
        body.append("csrfmiddlewaretoken", csrfToken());
        body.append("initial_position_m", String(last.initialPositionM));
        body.append("initial_velocity_m_s", String(last.initialVelocityMs));
        body.append("acceleration_m_s2", String(last.accelerationMs2));
        scenario.check.disabled = true;
        scenario.result.textContent = "Checking on the server…";
        fetch(url, { method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "fetch" }, body: body })
          .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
          .then(function (payload) {
            if (payload && payload.ok) {
              var lines = [payload.message];
              (payload.checks || []).forEach(function (c) {
                lines.push((c.met ? "✓ " : "✗ ") + c.description + " (" + c.detail + ")");
              });
              scenario.result.textContent = lines.join("  ");
            } else {
              scenario.result.textContent = (payload && payload.error) || "Could not check that.";
            }
          })
          .catch(function () { scenario.result.textContent = "Could not reach the server."; })
          .then(function () { scenario.check.disabled = false; });
      });
    }

    // --- "Challenge the AI" claim checker -----------------
    // Reveals neither the ground truth nor the explanation until the
    // student has picked True/False and written their own reasoning --
    // the point is committing to a judgement first, the same principle
    // the Predict step already uses.
    var claim = {
      select: q(instrument, "[data-claim-select]"),
      statement: q(instrument, "[data-claim-statement]"),
      reasoning: q(instrument, "[data-claim-reasoning]"),
      check: q(instrument, "[data-claim-check]"),
      result: q(instrument, "[data-claim-result]")
    };
    var claimData = {};
    try {
      claimData = JSON.parse(instrument.getAttribute("data-claims") || "{}");
    } catch (e) { claimData = {}; }
    var claimCheckBase = instrument.getAttribute("data-claim-check-base") || "";

    function claimAnswerInputs() {
      return qa(instrument, "input[name='lab-claim-answer']");
    }
    function renderClaim() {
      if (!claim.select) return;
      var c = claimData[claim.select.value];
      if (!c) return;
      if (claim.statement) claim.statement.textContent = c.statement;
      claimAnswerInputs().forEach(function (i) { i.checked = false; });
      if (claim.reasoning) claim.reasoning.value = "";
      if (claim.result) claim.result.textContent = "";
    }
    if (claim.select) {
      claim.select.addEventListener("change", renderClaim);
      renderClaim();
    }
    if (claim.check && claim.result) {
      claim.check.addEventListener("click", function () {
        if (!claim.select || !claimCheckBase) return;
        var chosen = claimAnswerInputs().filter(function (i) { return i.checked; })[0];
        if (!chosen) {
          claim.result.textContent = "Choose True or False first.";
          return;
        }
        var url = claimCheckBase.replace("CLAIM_ID", encodeURIComponent(claim.select.value));
        var body = new FormData();
        body.append("csrfmiddlewaretoken", csrfToken());
        body.append("answer", chosen.value);
        claim.check.disabled = true;
        claim.result.textContent = "Checking on the server…";
        fetch(url, { method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "fetch" }, body: body })
          .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
          .then(function (payload) {
            if (payload && payload.ok) {
              var verdict = payload.matched ? "You judged this correctly." : "Not quite.";
              var truth = "The claim is actually " + (payload.is_true ? "TRUE" : "FALSE") + ".";
              claim.result.textContent = verdict + " " + truth + " " + payload.explanation;
            } else {
              claim.result.textContent = (payload && payload.error) || "Could not check that.";
            }
          })
          .catch(function () { claim.result.textContent = "Could not reach the server."; })
          .then(function () { claim.check.disabled = false; });
      });
    }

    // --- "What if?" quick actions --------------------------
    // Each applies a validated parameter change through the simulation's own
    // clamped setters, then rewinds to t = 0 so the student predicts the change.
    qa(root, "[data-whatif]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var api = root.labInstance;
        if (!api || !last) return;
        var op = btn.getAttribute("data-whatif");
        if (op === "accel*2") api.setAccel(last.accelerationMs2 * 2);
        else if (op === "accel*-1") api.setAccel(last.accelerationMs2 * -1);
        else if (op === "v0=0") api.setV0(0);
        else if (op === "v0*-1") api.setV0(last.initialVelocityMs * -1);
        if (api.setTime) api.setTime(0);
        if (hud.motion) {
          hud.motion.textContent =
            "Changed. Predict what will happen, then press Play or step through the motion.";
        }
      });
    });

    // --- AI Lab Copilot link (reuses the existing Tutor) ---
    // Keeps the "Ask the AI Lab Copilot" link pointed at the Physics Tutor with
    // the current, structured setup as a pre-fill. Nothing is sent until the
    // student presses Send in the Tutor; the Tutor's own reasoning-first policy
    // decides how much to reveal. No renderer internals are ever included.
    var copilotLink = q(root, "[data-copilot-link]");
    var tutorBase = root.getAttribute("data-tutor-base") || "";
    var tutorLink = q(root, "[data-tutor-link]");

    function copilotPrefill(state) {
      return (
        "Physics Lab - Kinematics (straight-line motion).\n" +
        "My setup: x0 = " + fmt(state.initialPositionM, 1) + " m, v0 = " +
        fmt(state.initialVelocityMs, 1) + " m/s, a = " + fmt(state.accelerationMs2) + " m/s^2.\n" +
        "Right now at t = " + fmt(state.timeS, 1) + " s: position = " + fmt(state.positionM) +
        " m, velocity = " + fmt(state.velocityMs) + " m/s.\n" +
        "I am investigating this motion. What should I be noticing? " +
        "What is staying constant, and what is changing?"
      );
    }
    function refreshCopilot(state) {
      if (!copilotLink) return;
      // Once an experiment has been observed/explained, prefer the richer link
      // that experiment-flow.js builds (it carries ?experiment=<id>).
      var explained = tutorLink && (tutorLink.getAttribute("href") || "").indexOf("experiment=") !== -1;
      if (explained) {
        copilotLink.setAttribute("href", tutorLink.getAttribute("href"));
        return;
      }
      if (!tutorBase) return;
      copilotLink.setAttribute(
        "href",
        tutorBase + (tutorBase.indexOf("?") === -1 ? "?" : "&") +
          "prefill=" + encodeURIComponent(copilotPrefill(state))
      );
    }

    // --- graph point -> time (the graph doubles as a time selector) ---
    var graphSvg = q(root, "[data-lab-graph]");
    if (graphSvg && root.labInstance && root.labInstance.setTime) {
      graphSvg.style.cursor = "pointer";
      graphSvg.addEventListener("click", function (e) {
        if (!last) return;
        var box = graphSvg.getBoundingClientRect();
        // viewBox is 0..360 wide; the plotted area runs x = 40..348.
        var vx = ((e.clientX - box.left) / box.width) * 360;
        var frac = Math.max(0, Math.min(1, (vx - 40) / (348 - 40)));
        // Match kinematics.js's graph x-domain exactly: 0 .. max(1, current t).
        var tMax = Math.max(1, last.timeS || 0);
        root.labInstance.setTime(frac * tMax);
      });
    }

    root.addEventListener("lab:state", function (e) {
      onState(e.detail);
      refreshCopilot(e.detail);
    });
    if (root.labInstance && typeof root.labInstance.getState === "function") {
      var s0 = root.labInstance.getState();
      onState(s0);
      refreshCopilot(s0);
    }
  });
})(window, document);
