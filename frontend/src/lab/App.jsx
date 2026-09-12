import React from "react";

/**
 * Physics Lab React island -- deliberately passive and read-only.
 *
 * The Kinematics page already has five interacting vanilla-JS modules
 * (lab.js, kinematics.js, experiment-flow.js, lab-instrument.js,
 * kinematics-3d.js) that own every form, every button and the 3D view.
 * This component never attaches to any of that: it only renders a compact
 * reference card from data the server already computed (the equations for
 * this simulation type, and any scenario challenges), reusing the existing
 * `.lab-equation` / `.content-list` styles from app.css. Predict / Observe /
 * Explain still go through the plain HTML forms exactly as before.
 */
export default function LabApp({ initialState, rootEl }) {
  const equations = initialState.equations || [];
  const scenarios = initialState.scenarios || [];

  React.useEffect(() => {
    rootEl.hidden = false;
  }, [rootEl]);

  if (equations.length === 0 && scenarios.length === 0) {
    return null;
  }

  return (
    <React.Fragment>
      <p className="card-label">Quick reference</p>
      <h2>{initialState.simulationTitle}</h2>
      {equations.length > 0 && (
        <div className="lab-equation">
          <p className="lab-eq-general">
            {equations.map(function (eq, i) {
              return (
                <code key={i} style={{ display: "block", marginTop: i > 0 ? ".4rem" : 0 }}>
                  {eq}
                </code>
              );
            })}
          </p>
        </div>
      )}
      {scenarios.length > 0 && (
        <React.Fragment>
          <p className="card-label" style={{ marginTop: "1rem" }}>
            Challenges available in this lab
          </p>
          <ul className="content-list">
            {scenarios.map(function (s) {
              return <li key={s.scenario_id}>{s.title || s.scenario_id}</li>;
            })}
          </ul>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}
