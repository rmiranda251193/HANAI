import React from "react";
import { reactFetch } from "../shared/csrf.js";

const ROLE_LABEL = { student: "You", tutor: "Tutor", system: "System" };

function Turn({ message }) {
  return (
    <li className={"tutor-turn tutor-turn-" + message.role}>
      <p className="tutor-turn-role">
        {ROLE_LABEL[message.role] || message.role}
        {message.mode ? (
          <React.Fragment>
            {" · "}
            <span className="tutor-mode">{message.mode}</span>
          </React.Fragment>
        ) : null}
      </p>
      <p className="tutor-turn-text">{message.content}</p>
    </li>
  );
}

/**
 * A live chat replacement for the tutor conversation panel. Reveals itself
 * (and hides the server-rendered [data-tutor-static] section) only once it
 * has mounted successfully -- if this component throws, or the page's React
 * runtime is unavailable, the plain HTML form keeps working exactly as it
 * does today, one full-page POST per turn. This never talks to a second
 * tutor engine: `postUrl` is the exact same `students:tutor` endpoint the
 * HTML form posts to, just asked (via the X-HANAI-Client header) for JSON
 * instead of a full-page re-render.
 */
export default function TutorApp({ initialState, rootEl }) {
  const [conversation, setConversation] = React.useState(initialState.conversation || []);
  const [question, setQuestion] = React.useState(initialState.initialQuestion || "");
  const [error, setError] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const threadRef = React.useRef(null);

  React.useEffect(() => {
    rootEl.hidden = false;
    const staticSection = document.querySelector("[data-tutor-static]");
    if (staticSection) staticSection.hidden = true;
  }, [rootEl]);

  React.useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [conversation]);

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError("");
    reactFetch(initialState.postUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ action: "ask", question: trimmed }).toString(),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        const data = result.data;
        if (!result.ok || !data.ok) {
          setError((data && data.error) || "Your tutor could not respond. Please try again.");
          return;
        }
        setConversation(data.conversation || []);
        setQuestion("");
      })
      .catch(function () {
        setError("Your tutor could not respond. Please try again.");
      })
      .finally(function () {
        setSending(false);
      });
  }

  return (
    <React.Fragment>
      <p className="card-label">Conversation</p>
      <h2>Ask, think, attempt</h2>

      {error && (
        <p className="field-errors" role="alert">
          {error}
        </p>
      )}

      {conversation.length > 0 ? (
        <ol className="tutor-thread" ref={threadRef} style={{ maxHeight: "26rem", overflowY: "auto" }}>
          {conversation.map(function (message, i) {
            return <Turn key={i} message={message} />;
          })}
        </ol>
      ) : (
        <p className="tutor-empty">No messages yet. Ask your first question below to begin.</p>
      )}

      <form className="tutor-composer" onSubmit={handleSubmit}>
        <label htmlFor="react-tutor-question">Ask Physics Tutor</label>
        <textarea
          id="react-tutor-question"
          rows={3}
          placeholder="e.g. What is acceleration?"
          value={question}
          onChange={function (e) {
            setQuestion(e.target.value);
          }}
        />
        <button type="submit" className="button button-primary" disabled={sending}>
          {sending ? "Sending…" : "Send"}
        </button>
      </form>
    </React.Fragment>
  );
}
