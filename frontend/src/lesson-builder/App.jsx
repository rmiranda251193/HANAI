import React from "react";
import { reactFetch } from "../shared/csrf.js";

/**
 * A quick activity manager: the same activity list as Section 4 below, with
 * a delete action that doesn't reload the page. It calls the exact same
 * `lessons:activity_delete` endpoint the server-rendered delete form below
 * already posts to (owner check, validation and all) -- just asked, via the
 * X-HANAI-Client header, for a small JSON acknowledgement instead of a
 * redirect. Adding, editing, reordering, AI assistance, review and publish
 * all stay exactly where they are: the full Section 4 (and the rest of the
 * builder) below this panel, unchanged.
 */
export default function LessonBuilderApp({ initialState, rootEl }) {
  const [activities, setActivities] = React.useState(initialState.activities || []);
  const [error, setError] = React.useState("");
  const [pendingId, setPendingId] = React.useState(null);

  React.useEffect(() => {
    rootEl.hidden = false;
  }, [rootEl]);

  function handleDelete(activity) {
    if (pendingId) return;
    if (!window.confirm('Delete "' + activity.title + '"? This cannot be undone.')) return;
    setPendingId(activity.id);
    setError("");
    reactFetch(activity.deleteUrl, { method: "POST" })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          setError((result.data && result.data.error) || "That activity could not be deleted.");
          return;
        }
        setActivities(result.data.activities || []);
      })
      .catch(function () {
        setError("That activity could not be deleted. Please try again.");
      })
      .finally(function () {
        setPendingId(null);
      });
  }

  if (activities.length === 0) {
    return null;
  }

  return (
    <React.Fragment>
      <p className="card-label">Quick activity manager</p>
      <h2>Learning activities at a glance</h2>
      {error && (
        <p className="field-errors" role="alert">
          {error}
        </p>
      )}
      <ol className="lb-activity-list">
        {activities.map(function (activity) {
          return (
            <li className="lb-activity" key={activity.id}>
              <div className="lb-activity-head">
                <span className="lb-activity-num" aria-hidden="true">
                  {activity.position}
                </span>
                <span className="status-badge">{activity.activityTypeLabel}</span>
                <span className="lb-activity-title">{activity.title}</span>
              </div>
              {activity.instructions ? (
                <p className="lb-activity-instructions">{activity.instructions}</p>
              ) : null}
              <div className="lb-activity-actions">
                <button
                  type="button"
                  className="button button-danger"
                  disabled={pendingId === activity.id}
                  onClick={function () {
                    handleDelete(activity);
                  }}
                >
                  {pendingId === activity.id ? "Deleting…" : "Delete"}
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </React.Fragment>
  );
}
