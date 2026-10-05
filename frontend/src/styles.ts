/** Styles: Home Assistant theme variables only, so light/dark/custom themes just work. */
export const styles = `
:host {
  display: block;
  min-height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, sans-serif));
  --tp-radius: var(--ha-card-border-radius, 12px);
  --tp-border: 1px solid var(--divider-color);
  --tp-muted: var(--secondary-text-color);
  --tp-accent: var(--primary-color);
  --tp-warn: var(--warning-color, #f4b400);
  --tp-bad: var(--error-color, #db4437);
  --tp-good: var(--success-color, #43a047);
}
* { box-sizing: border-box; }
button { font: inherit; }
.toolbar {
  display: flex; align-items: center; gap: 4px;
  height: var(--header-height, 56px);
  padding: 0 12px;
  background: var(--app-header-background-color, var(--primary-background-color));
  color: var(--app-header-text-color, var(--primary-text-color));
  border-bottom: var(--app-header-border-bottom, var(--tp-border));
  position: sticky; top: 0; z-index: 2;
}
.toolbar .title { font-size: 20px; font-weight: 400; margin-inline-start: 8px; flex: 1; }
.tabs { display: flex; gap: 4px; }
.tab {
  border: none; background: none; color: inherit; cursor: pointer;
  padding: 8px 12px; border-radius: 18px; opacity: .75;
}
.tab[aria-selected="true"] { opacity: 1; background: rgba(var(--rgb-primary-color, 3,169,244), .14); color: var(--tp-accent); }
.content { max-width: 920px; margin: 0 auto; padding: 16px 16px 96px; }

/* The swap strip: the one visual that explains the product. */
.swap {
  display: grid; grid-template-columns: 1fr auto 1fr; align-items: stretch; gap: 12px;
  margin: 8px 0 20px;
}
.slot {
  border: var(--tp-border); border-radius: var(--tp-radius);
  background: var(--card-background-color); padding: 14px 16px; min-height: 76px;
}
.slot.empty { border-style: dashed; color: var(--tp-muted); display: flex; align-items: center; }
.slot.current { border-color: var(--tp-accent); box-shadow: 0 0 0 1px var(--tp-accent) inset; }
.slot .label { font-size: 12px; color: var(--tp-muted); margin-bottom: 4px; }
.slot .name { font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
.slot .meta { font-size: 13px; color: var(--tp-muted); margin-top: 2px; }
.arrow { display: flex; align-items: center; justify-content: center; color: var(--tp-accent); }
.arrow svg { width: 28px; height: 28px; }

.steps { display: flex; gap: 6px; margin: 4px 0 16px; padding: 0; list-style: none; flex-wrap: wrap; }
.steps li { font-size: 13px; color: var(--tp-muted); padding: 4px 10px; border-radius: 12px; border: var(--tp-border); }
.steps li.active { color: var(--tp-accent); border-color: var(--tp-accent); }
.steps li.done { color: var(--primary-text-color); }

h2 { font-size: 22px; font-weight: 400; margin: 8px 0 4px; }
.lead { color: var(--tp-muted); margin: 0 0 16px; line-height: 1.5; max-width: 70ch; }

.card {
  background: var(--card-background-color); border: var(--tp-border);
  border-radius: var(--tp-radius); overflow: hidden; margin-bottom: 16px;
}
.search {
  width: 100%; padding: 12px 14px; border: none; border-bottom: var(--tp-border);
  background: transparent; color: inherit; font: inherit; outline: none;
}
.search:focus { box-shadow: 0 -2px 0 var(--tp-accent) inset; }
.row {
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 12px 16px; border: none; background: none; color: inherit; text-align: start;
  border-bottom: var(--tp-border); cursor: pointer;
}
.row:last-child { border-bottom: none; }
.row:hover, .row:focus-visible { background: var(--secondary-background-color); outline: none; }
.row .main { flex: 1; min-width: 0; }
.row .name { font-weight: 500; overflow-wrap: anywhere; }
.row .meta { font-size: 13px; color: var(--tp-muted); }
.count { font-size: 13px; color: var(--tp-muted); white-space: nowrap; }
.count strong { color: var(--primary-text-color); font-weight: 500; }
.badge {
  font-size: 12px; padding: 2px 8px; border-radius: 10px; white-space: nowrap;
  border: 1px solid currentColor;
}
.badge.offline { color: var(--tp-bad); }
.badge.hint { color: var(--tp-accent); }
.empty-note { padding: 20px 16px; color: var(--tp-muted); }

.usage-group { padding: 12px 16px; border-bottom: var(--tp-border); }
.usage-group:last-child { border-bottom: none; }
.usage-group h3 { margin: 0 0 6px; font-size: 14px; font-weight: 500; }
.usage-group ul { margin: 0; padding-inline-start: 18px; }
.usage-group li { margin: 2px 0; }
a, .link { color: var(--tp-accent); text-decoration: none; cursor: pointer; background: none; border: none; padding: 0; font: inherit; }
a:hover, .link:hover { text-decoration: underline; }

.map { width: 100%; border-collapse: collapse; }
.map th { text-align: start; font-size: 12px; font-weight: 500; color: var(--tp-muted); padding: 10px 16px; border-bottom: var(--tp-border); }
.map td { padding: 10px 16px; border-bottom: var(--tp-border); vertical-align: middle; }
.map tr:last-child td { border-bottom: none; }
.map .eid { font-family: var(--code-font-family, monospace); font-size: 12px; color: var(--tp-muted); overflow-wrap: anywhere; }
.map select {
  width: 100%; padding: 8px; border-radius: 8px; border: var(--tp-border);
  background: var(--card-background-color); color: inherit; font: inherit;
}
.conf { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-inline-end: 6px; }
.conf.high { background: var(--tp-good); }
.conf.medium { background: var(--tp-warn); }
.conf.low, .conf.none { background: var(--divider-color); }

.headline { font-size: 28px; font-weight: 400; margin: 4px 0 4px; }
.headline + .lead { margin-bottom: 20px; }
.item { border-bottom: var(--tp-border); }
.item:last-child { border-bottom: none; }
.item summary {
  list-style: none; cursor: pointer; padding: 12px 16px;
  display: flex; gap: 12px; align-items: center;
}
.item summary::-webkit-details-marker { display: none; }
.item summary .name { flex: 1; font-weight: 500; overflow-wrap: anywhere; }
.item .kind { font-size: 12px; color: var(--tp-muted); text-transform: capitalize; }
.changes { margin: 0; padding: 0 16px 12px; list-style: none; }
.changes li { padding: 6px 0; border-top: var(--tp-border); font-size: 13px; }
.changes .path { font-family: var(--code-font-family, monospace); color: var(--tp-muted); font-size: 12px; overflow-wrap: anywhere; }
.diff { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; font-family: var(--code-font-family, monospace); font-size: 12px; }
.diff .old { text-decoration: line-through; color: var(--tp-bad); overflow-wrap: anywhere; }
.diff .new { color: var(--tp-good); overflow-wrap: anywhere; }
.notice { padding: 12px 16px; border-radius: var(--tp-radius); margin-bottom: 16px; line-height: 1.5; border: 1px solid; }
.notice.warn { border-color: var(--tp-warn); background: rgba(244, 180, 0, .08); }
.notice.bad { border-color: var(--tp-bad); background: rgba(219, 68, 55, .08); }
.notice.good { border-color: var(--tp-good); background: rgba(67, 160, 71, .08); }
.notice ul { margin: 6px 0 0; padding-inline-start: 18px; }

.actions {
  position: sticky; bottom: 0; display: flex; gap: 8px; justify-content: flex-end;
  padding: 12px 16px; margin: 0 -16px;
  background: var(--primary-background-color); border-top: var(--tp-border);
}
.btn {
  border-radius: 20px; padding: 10px 18px; cursor: pointer; border: 1px solid var(--tp-accent);
  background: transparent; color: var(--tp-accent); font-weight: 500;
}
.btn.primary { background: var(--tp-accent); color: var(--text-primary-color, #fff); }
.btn.danger { border-color: var(--tp-bad); color: var(--tp-bad); }
.btn:disabled { opacity: .45; cursor: default; }
.btn:focus-visible, .row:focus-visible, .tab:focus-visible { outline: 2px solid var(--tp-accent); outline-offset: 2px; }

.history .row { cursor: default; }
.spinner { padding: 32px; text-align: center; color: var(--tp-muted); }

@media (max-width: 640px) {
  .swap { grid-template-columns: 1fr; }
  .arrow { transform: rotate(90deg); height: 28px; }
  .content { padding: 12px 12px 96px; }
  .actions { margin: 0 -12px; }
  .map th:nth-child(3), .map td:nth-child(3) { display: none; }
  .headline { font-size: 24px; }
}
`;
