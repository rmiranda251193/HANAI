/**
 * Fetch helper for the React islands. Every request is same-origin, carries
 * the same CSRF token Django's own forms use (read from the `csrftoken`
 * cookie the existing `{% csrf_token %}` tags already cause to be set), and
 * is tagged with the header the server-side views check for before ever
 * returning JSON instead of their normal HTML response (see
 * config/react_bridge.py). No new trust boundary is introduced: this is the
 * same CSRF protection, the same session, the same server-side validation
 * every existing form already goes through.
 */

export function getCookie(name) {
  const match = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
  return match ? decodeURIComponent(match.pop()) : "";
}

export function reactFetch(url, options) {
  options = options || {};
  const headers = Object.assign(
    {
      "X-HANAI-Client": "react",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    options.headers || {}
  );
  return fetch(
    url,
    Object.assign({ credentials: "same-origin" }, options, { headers })
  );
}
