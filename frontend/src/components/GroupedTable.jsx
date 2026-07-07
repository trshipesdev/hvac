import React from "react";

// A table with a header row per group (e.g. one month) followed by that
// group's individual rows (e.g. one per unit) — so related rows read as
// visually connected instead of a flat, hard-to-scan list. Columns/rendering
// are fully supplied by the caller; this only owns the grouping structure.
export function GroupedTable({ columns, groups, renderGroupHeader, renderRow, rowKey }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300">
          {columns.map((c) => (
            <th key={c.key} className={c.className || "text-left py-3 px-4"}>{c.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <React.Fragment key={g.key}>
            <tr className="bg-paper-100/60 border-b border-paper-300" data-testid={`group-header-${g.key}`}>
              <td colSpan={columns.length} className="py-2.5 px-6">
                {renderGroupHeader(g)}
              </td>
            </tr>
            {g.rows.map((row, i) => (
              <tr key={rowKey(row, i)} className="border-b border-paper-200 hover:bg-paper-50 transition-colors">
                {renderRow(row, g)}
              </tr>
            ))}
          </React.Fragment>
        ))}
        {groups.length === 0 && (
          <tr><td colSpan={columns.length} className="p-10 text-center text-slate-500">No data yet.</td></tr>
        )}
      </tbody>
    </table>
  );
}
