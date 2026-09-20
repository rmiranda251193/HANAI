/* Progressive enhancement for the lesson builder's "Add activity" form.
 * The server is authoritative: this only hides options that do not apply to
 * the chosen activity type so the teacher is not scrolling a long list. With
 * JavaScript disabled the full grouped <select> still works. */
(() => {
  "use strict";
  const form = document.querySelector("[data-add-activity]");
  if (!form) return;

  const typeSelect = form.querySelector("[data-activity-type]");
  const refSelect = form.querySelector("#lb-new-ref");
  const focusGroup = form.querySelector("[data-focus-group]");
  const refGroup = form.querySelector("[data-ref-group]");
  if (!typeSelect) return;

  const REFERENCED = new Set(["physics_lab", "practice", "assessment", "recovery", "scenario"]);

  function apply() {
    const type = typeSelect.value;
    const needsRef = REFERENCED.has(type);
    const isTutor = type === "tutor";

    if (focusGroup) focusGroup.hidden = !isTutor;
    if (refGroup) refGroup.hidden = !needsRef;

    if (refSelect) {
      Array.from(refSelect.querySelectorAll("optgroup")).forEach((group) => {
        const match = group.dataset.refType === type;
        group.hidden = !match;
        Array.from(group.children).forEach((opt) => {
          opt.disabled = !match;
        });
      });
      const current = refSelect.selectedOptions[0];
      if (needsRef && current && current.disabled) refSelect.value = "";
      if (!needsRef) refSelect.value = "";
    }
  }

  typeSelect.addEventListener("change", apply);
  apply();
})();
