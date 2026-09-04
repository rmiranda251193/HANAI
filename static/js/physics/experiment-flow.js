/**
 * Physics Lab experiment learning-flow.
 *
 * Wires the Predict / Observe / Explain forms to their server endpoints. It does
 * NOT compute physics -- the deterministic values come from the simulation
 * (static/js/physics/newtons-second-law.js) and are recomputed again on the
 * server. This file only submits meaningful learning moments and reflects the
 * server's response in the page.
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

  ready(function () {
    var root = document.querySelector(".lab.lab-flow");
    if (!root) return;

    function currentValues() {
      var instance = root.labInstance;
      if (instance && typeof instance.getState === "function") {
        var s = instance.getState();
        return { mass: s.massKg, force: s.forceN, state: s };
      }
      var massEl = root.querySelector("[data-input-mass]");
      var forceEl = root.querySelector("[data-input-force]");
      return {
        mass: massEl ? parseFloat(massEl.value) : null,
        force: forceEl ? parseFloat(forceEl.value) : null,
        state: null
      };
    }

    function syncHiddenFields() {
      var v = currentValues();

      // Legacy Newton's Second Law convention (unchanged).
      var massFields = root.querySelectorAll("[data-field-mass]");
      var forceFields = root.querySelectorAll("[data-field-force]");
      var i;
      for (i = 0; i < massFields.length; i++) {
        if (v.mass != null && isFinite(v.mass)) massFields[i].value = String(v.mass);
      }
      for (i = 0; i < forceFields.length; i++) {
        if (v.force != null && isFinite(v.force)) forceFields[i].value = String(v.force);
      }

      // Generic convention for any other simulation: a hidden input with
      // data-field="<getState() key>" is synced from the live sim state
      // directly, with no per-simulation code needed here.
      if (v.state) {
        var genericFields = root.querySelectorAll("[data-field]");
        for (i = 0; i < genericFields.length; i++) {
          var key = genericFields[i].getAttribute("data-field");
          var value = key ? v.state[key] : null;
          if (value != null && isFinite(value)) genericFields[i].value = String(value);
        }
      }
    }

    // Keep the hidden mass/force fields in step with the live simulation.
    root.addEventListener("lab:state", syncHiddenFields);
    syncHiddenFields();

    function resultNode(name) {
      return root.querySelector('[data-step-result="' + name + '"]');
    }

    function setResult(name, text, isError) {
      var node = resultNode(name);
      if (!node) return;
      node.textContent = text;
      node.classList.toggle("is-error", !!isError);
    }

    function submitForm(form, name) {
      syncHiddenFields();
      var button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      setResult(name, "Saving…", false);

      var data = new FormData(form);

      fetch(form.getAttribute("action"), {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        credentials: "same-origin",
        body: data
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              return { ok: false, error: "Unexpected response from the server." };
            })
            .then(function (payload) {
              return { status: response.status, payload: payload };
            });
        })
        .then(function (result) {
          var payload = result.payload || {};
          if (result.status >= 200 && result.status < 300 && payload.ok) {
            setResult(name, payload.message || "Saved.", false);
            if (name === "explain" && payload.tutor_url) {
              var link = root.querySelector("[data-tutor-link]");
              if (link) link.setAttribute("href", payload.tutor_url);
            }
          } else {
            setResult(
              name,
              payload.error || "That could not be saved. Please try again.",
              true
            );
          }
        })
        .catch(function () {
          setResult(name, "Could not reach the server. Please try again.", true);
        })
        .then(function () {
          if (button) button.disabled = false;
        });
    }

    var forms = root.querySelectorAll("form[data-experiment-form]");
    for (var i = 0; i < forms.length; i++) {
      (function (form) {
        form.addEventListener("submit", function (event) {
          event.preventDefault();
          submitForm(form, form.getAttribute("data-experiment-form"));
        });
      })(forms[i]);
    }
  });
})(window, document);
