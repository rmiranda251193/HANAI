/**
 * A thin fixed progress bar showing how far the student has scrolled through
 * the Predict -> Experiment -> Observe -> Explain -> Tutor step flow.
 *
 * Presentation only: it reads window scroll position and the .lab-flow
 * container's own bounding box, and writes to nothing but its own bar. It
 * never touches lab state, forms, or the four other Physics Lab scripts --
 * zero shared DOM, zero shared events, so it cannot conflict with them.
 */
(function () {
  "use strict";

  var fill = document.getElementById("labProgressFill");
  var flow = document.querySelector(".lab.lab-flow");
  if (!fill || !flow) return;

  var ticking = false;

  function update() {
    var rect = flow.getBoundingClientRect();
    var total = rect.height - window.innerHeight;
    var scrolled = Math.min(Math.max(-rect.top, 0), Math.max(total, 0));
    var progress = total > 0 ? scrolled / total : 0;
    fill.style.width = (progress * 100).toFixed(1) + "%";
    ticking = false;
  }

  window.addEventListener(
    "scroll",
    function () {
      if (!ticking) {
        window.requestAnimationFrame(update);
        ticking = true;
      }
    },
    { passive: true }
  );
  window.addEventListener("resize", update);
  update();
})();
