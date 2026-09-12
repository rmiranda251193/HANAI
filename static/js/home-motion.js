/**
 * Home page motion: a restrained scroll parallax on two decorative layers
 * behind the hero, and a fade/rise reveal for the sections below it.
 *
 * Presentation only -- no Physics, no state, nothing recorded, nothing this
 * depends on. Progressive: every element is fully visible without this
 * script (the "js-reveal-ready" class that hides [data-reveal] elements
 * pending their reveal is added by this script itself, never present in the
 * server-rendered HTML), and prefers-reduced-motion disables both effects.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- reveal-on-scroll (foundation-grid cards, home-flow) ----------------
  var revealEls = document.querySelectorAll("[data-reveal]");
  if (revealEls.length && !reduced && "IntersectionObserver" in window) {
    document.documentElement.classList.add("js-reveal-ready");
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-revealed");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.2, rootMargin: "0px 0px -10% 0px" }
    );
    revealEls.forEach(function (el) {
      io.observe(el);
    });
  }

  // ---- hero parallax -------------------------------------------------------
  var layers = document.querySelectorAll("[data-parallax-depth]");
  if (layers.length && !reduced) {
    var ticking = false;
    function apply() {
      var y = window.scrollY || window.pageYOffset || 0;
      layers.forEach(function (el) {
        var depth = parseFloat(el.getAttribute("data-parallax-depth")) || 0;
        el.style.transform = "translate3d(0," + (y * depth).toFixed(2) + "px,0)";
      });
      ticking = false;
    }
    window.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          window.requestAnimationFrame(apply);
          ticking = true;
        }
      },
      { passive: true }
    );
    apply();
  }
})();
