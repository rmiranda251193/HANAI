// Executes each built bundle against a simulated DOM (jsdom) with a
// realistic bootstrap payload, the same vendored React/ReactDOM UMD builds
// the real pages load, and a stubbed same-origin `fetch`. This is not a
// browser and it is not a substitute for opening the real pages, but it
// does catch the class of bug that "it compiled" cannot: a runtime
// exception, a mount that never reveals itself, or a bad DOM API call.
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const reactSrc = readFileSync(root + "../static/js/vendor/react-18.3.1.production.min.js", "utf8");
const reactDomSrc = readFileSync(root + "../static/js/vendor/react-dom-18.3.1.production.min.js", "utf8");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run(name, mountId, state, extraHtml) {
  const html = `<!doctype html><html><body>
    <div id="${mountId}" data-state='${JSON.stringify(state).replace(/'/g, "&#x27;")}' hidden></div>
    ${extraHtml || ""}
  </body></html>`;

  const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/" });
  const { window } = dom;
  window.fetch = async () => ({
    ok: true,
    json: async () => ({ ok: true, conversation: [], activities: [] }),
  });
  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.error || e.message));

  window.eval(reactSrc);
  window.eval(reactDomSrc);
  const bundleSrc = readFileSync(root + `../static/react/${name}.js`, "utf8");
  window.eval(bundleSrc);

  await sleep(50); // let React flush its passive effects (useEffect)

  const mount = window.document.getElementById(mountId);
  const revealed = mount.hidden === false;
  console.log(`${name}.js: ${errors.length === 0 ? "no errors" : "ERRORS: " + errors.join("; ")}, revealed=${revealed}`);
  if (errors.length > 0) {
    process.exitCode = 1;
  }
  return { revealed, errors, window };
}

const results = {};

results.lab = await run("lab", "react-lab-root", {
  simulationSlug: "kinematics",
  simulationTitle: "Kinematics Lab",
  equations: ["v = v0 + a t", "x = x0 + v0 t + 1/2 a t^2"],
  scenarios: [{ scenario_id: "reach-20m", title: "Reach 20 m before 5 s" }],
  defaults: {},
  bounds: {},
  endpoints: {},
});

results.tutor = await run(
  "tutor",
  "react-tutor-root",
  {
    lessonSlug: "motion-basics",
    initialQuestion: "",
    postUrl: "/student/tutor/motion-basics/",
    conversation: [{ role: "student", content: "What is velocity?", mode: "", createdAt: "2026-01-01T00:00:00Z" }],
  },
  '<section data-tutor-static><p>static fallback</p></section>'
);
{
  const staticSection = results.tutor.window.document.querySelector("[data-tutor-static]");
  const hidStatic = staticSection && staticSection.hidden === true;
  console.log(`tutor.js: static fallback hidden after mount = ${hidStatic}`);
  if (!hidStatic) process.exitCode = 1;

  // Simulate sending a message: type into the textarea and submit the form.
  const { window } = results.tutor;
  const doc = window.document;
  const textarea = doc.getElementById("react-tutor-question");
  const form = textarea.closest("form");
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  nativeSetter.call(textarea, "Why does it accelerate?");
  textarea.dispatchEvent(new window.Event("input", { bubbles: true }));
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await sleep(50);
  console.log("tutor.js: submit handler ran with no thrown error (mocked fetch resolved).");
}

results.analytics = await run("analytics", "react-analytics-root", {
  studentCount: 3,
  activeStudentCount: 2,
  conceptSummary: [{ concept: "Velocity", topic: "Kinematics", students_engaged: 2, lesson_linked_evidence: 4, practice_attempts: 5, practice_correct: 3 }],
  misconceptionSummary: [],
  attentionSignals: [{ student: "Alex", band: "Needs attention", signals: ["No recent evidence"] }],
  recoverySummary: [],
  assessmentSummary: [],
  practiceSummary: [],
  physicsLabSummary: [],
  simulationUsage: [],
  tutorSummary: [],
  activityTypeSummary: [],
  notes: [],
  rangeLabel: "Last 30 days",
  filterNotices: [],
});

results["lesson-builder"] = await run("lesson-builder", "react-lesson-builder-root", {
  lessonSlug: "forces-and-motion",
  activities: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      position: 1,
      activityType: "physics_lab",
      activityTypeLabel: "Physics Lab",
      title: "Run the Lab",
      instructions: "",
      deleteUrl: "/lessons/forces-and-motion/build/activities/11111111-1111-1111-1111-111111111111/delete/",
    },
  ],
});
{
  // Simulate clicking Delete on the lesson-builder island (mocked fetch,
  // and window.confirm must be stubbed since jsdom has no real dialog).
  const { window } = results["lesson-builder"];
  window.confirm = () => true;
  const button = window.document.querySelector(".lb-activity-actions button");
  button.dispatchEvent(new window.Event("click", { bubbles: true }));
  await sleep(50);
  console.log("lesson-builder.js: delete click handler ran with no thrown error (mocked fetch resolved).");
}

const failed = Object.entries(results).filter(([, r]) => r.errors.length > 0 || !r.revealed);
if (failed.length > 0) {
  console.error("FAILED:", failed.map(([name]) => name).join(", "));
  process.exitCode = 1;
} else {
  console.log("All four islands mounted and revealed themselves with no errors.");
}
