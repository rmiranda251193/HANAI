import React from "react";

/**
 * Interactive cohort explorer -- a sortable/filterable view over the exact
 * same rows already rendered as plain HTML tables further down the page.
 * Everything here is client-side over the JSON the server embedded (no
 * fetch, no new endpoint, no query at all): this only adds interactivity a
 * static table can't offer, it never recomputes or reinterprets a number.
 * Changing the date range / student / lesson / concept filters still uses
 * the existing form above and reloads the page, exactly as today.
 */

const DATASETS = [
  { key: "conceptSummary", label: "Concepts", columns: ["concept", "topic", "students_engaged", "lesson_linked_evidence", "practice_attempts", "practice_correct"] },
  { key: "misconceptionSummary", label: "Misconceptions", columns: ["code", "title", "concept", "students_affected", "candidates", "confirmed"] },
  { key: "attentionSignals", label: "Students to review", columns: ["student", "band", "signals"] },
];

function cellText(value) {
  if (Array.isArray(value)) return value.join("; ");
  if (value === null || value === undefined) return "";
  return String(value);
}

function SortableTable({ rows, columns }) {
  const [sortKey, setSortKey] = React.useState(columns[0]);
  const [ascending, setAscending] = React.useState(true);

  const sorted = React.useMemo(function () {
    const copy = rows.slice();
    copy.sort(function (a, b) {
      const av = cellText(a[sortKey]).toLowerCase();
      const bv = cellText(b[sortKey]).toLowerCase();
      const aNum = Number(a[sortKey]);
      const bNum = Number(b[sortKey]);
      let cmp;
      if (!Number.isNaN(aNum) && !Number.isNaN(bNum) && a[sortKey] !== "" && b[sortKey] !== "") {
        cmp = aNum - bNum;
      } else {
        cmp = av < bv ? -1 : av > bv ? 1 : 0;
      }
      return ascending ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, ascending]);

  function toggleSort(col) {
    if (col === sortKey) {
      setAscending(!ascending);
    } else {
      setSortKey(col);
      setAscending(true);
    }
  }

  if (rows.length === 0) {
    return <p className="empty-state-inline">No rows for this view.</p>;
  }

  return (
    <div className="tw-analytics-scroll">
      <table className="tw-analytics-table">
        <thead>
          <tr>
            {columns.map(function (col) {
              const active = col === sortKey;
              return (
                <th key={col} scope="col">
                  <button
                    type="button"
                    className="button-ghost"
                    style={{ padding: ".2rem .4rem", minHeight: "auto", font: "inherit" }}
                    onClick={function () {
                      toggleSort(col);
                    }}
                    aria-label={"Sort by " + col}
                  >
                    {col.replace(/_/g, " ")}
                    {active ? (ascending ? " ▲" : " ▼") : ""}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map(function (row, i) {
            return (
              <tr key={i}>
                {columns.map(function (col) {
                  return <td key={col}>{cellText(row[col])}</td>;
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalyticsApp({ initialState, rootEl }) {
  const [datasetKey, setDatasetKey] = React.useState(DATASETS[0].key);

  React.useEffect(() => {
    rootEl.hidden = false;
  }, [rootEl]);

  const dataset = DATASETS.find(function (d) {
    return d.key === datasetKey;
  });
  const rows = initialState[datasetKey] || [];

  return (
    <React.Fragment>
      <p className="card-label">Interactive explorer</p>
      <h2>Sort and scan the cohort data</h2>
      <p className="tw-analytics-lede">
        The same rows as the tables below, sortable by any column. Nothing here is
        recomputed &mdash; it is the exact snapshot the server already built for{" "}
        {initialState.rangeLabel}.
      </p>
      <p className="lib-field" style={{ maxWidth: "18rem" }}>
        <label htmlFor="react-analytics-dataset">View</label>
        <select
          id="react-analytics-dataset"
          value={datasetKey}
          onChange={function (e) {
            setDatasetKey(e.target.value);
          }}
        >
          {DATASETS.map(function (d) {
            return (
              <option key={d.key} value={d.key}>
                {d.label}
              </option>
            );
          })}
        </select>
      </p>
      <SortableTable rows={rows} columns={dataset.columns} />
    </React.Fragment>
  );
}
