/**
 * Transplant sidebar panel.
 *
 * Flow: old device → new device → match entities → review → done (undo).
 * No framework: a small render() over a plain state object keeps the
 * bundle tiny and dependency-free.
 */

import {
  type ApplyResult,
  type DeviceSummary,
  errorMessage,
  type HomeAssistant,
  type Overview,
  type Plan,
  type Suggestion,
  TransplantApi,
  type UsageItem,
} from "./api.js";
import { editorPath, h, navigate, plural, typeLabel } from "./dom.js";
import { styles } from "./styles.js";

type Step = "old" | "new" | "match" | "review" | "done";
type Tab = "replace" | "history";

interface State {
  tab: Tab;
  step: Step;
  loading: boolean;
  busy: boolean;
  error: string | null;
  overview: Overview | null;
  query: string;
  oldDevice: DeviceSummary | null;
  newDevice: DeviceSummary | null;
  usage: UsageItem[] | null;
  suggestion: Suggestion | null;
  mapping: Record<string, string | null>;
  plan: Plan | null;
  result: ApplyResult | null;
  undone: boolean;
  notice: string | null;
}

const STEPS: { id: Step; label: string }[] = [
  { id: "old", label: "1 Old device" },
  { id: "new", label: "2 New device" },
  { id: "match", label: "3 Match entities" },
  { id: "review", label: "4 Review" },
  { id: "done", label: "5 Done" },
];
const MAX_ROWS = 150;

const ARROW = (): SVGElement => {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("fill", "currentColor");
  path.setAttribute("d", "M4 11h12.17l-5.59-5.59L12 4l8 8-8 8-1.41-1.41L16.17 13H4z");
  svg.appendChild(path);
  return svg;
};

function initialState(): State {
  return {
    tab: "replace",
    step: "old",
    loading: true,
    busy: false,
    error: null,
    overview: null,
    query: "",
    oldDevice: null,
    newDevice: null,
    usage: null,
    suggestion: null,
    mapping: {},
    plan: null,
    result: null,
    undone: false,
    notice: null,
  };
}

class TransplantPanel extends HTMLElement {
  private _hass: HomeAssistant | null = null;
  private _narrow = false;
  private api: TransplantApi | null = null;
  private state: State = initialState();
  private readonly root: ShadowRoot;
  private focusSearch = false;

  constructor() {
    super();
    this.root = this.attachShadow({ mode: "open" });
  }

  // HA sets `hass` on every state change: store it, never re-render for it.
  set hass(hass: HomeAssistant) {
    const first = this._hass === null;
    this._hass = hass;
    this.api = new TransplantApi(hass);
    if (first) void this.loadOverview();
    const menu = this.root.querySelector("ha-menu-button") as (HTMLElement & { hass?: unknown }) | null;
    if (menu) menu.hass = hass;
  }

  set narrow(value: boolean) {
    if (value !== this._narrow) {
      this._narrow = value;
      this.render();
    }
  }

  set panel(_value: unknown) {
    /* config not needed */
  }

  connectedCallback(): void {
    this.render();
  }

  // ---- state helpers --------------------------------------------------

  private set(patch: Partial<State>): void {
    this.state = { ...this.state, ...patch };
    this.render();
  }

  private async run<T>(work: () => Promise<T>): Promise<T | undefined> {
    this.set({ busy: true, error: null });
    try {
      return await work();
    } catch (err) {
      this.set({ error: errorMessage(err) });
      return undefined;
    } finally {
      this.set({ busy: false });
    }
  }

  private async loadOverview(): Promise<void> {
    if (!this.api) return;
    this.set({ loading: true, error: null });
    try {
      this.set({ overview: await this.api.overview(), loading: false });
    } catch (err) {
      this.set({ loading: false, error: errorMessage(err) });
    }
  }

  private reset(): void {
    const overview = this.state.overview;
    this.state = { ...initialState(), overview, loading: false };
    void this.loadOverview();
  }

  // ---- actions --------------------------------------------------------

  private async pickOld(device: DeviceSummary): Promise<void> {
    const api = this.api;
    if (!api) return;
    const usage = await this.run(() => api.deviceUsage(device.id));
    if (usage) {
      this.set({ oldDevice: device, usage: usage.items, step: "new", query: "" });
      this.focusSearch = true;
    }
  }

  private async pickNew(device: DeviceSummary): Promise<void> {
    const api = this.api;
    const old = this.state.oldDevice;
    if (!api || !old) return;
    const suggestion = await this.run(() => api.suggest(old.id, device.id));
    if (suggestion) {
      const mapping: Record<string, string | null> = {};
      for (const match of suggestion.matches) mapping[match.old_entity_id] = match.new_entity_id;
      this.set({ newDevice: device, suggestion, mapping, step: "match" });
    }
  }

  private async preview(): Promise<void> {
    const api = this.api;
    const { oldDevice, newDevice, mapping } = this.state;
    if (!api || !oldDevice || !newDevice) return;
    const plan = await this.run(() => api.preview(oldDevice.id, newDevice.id, mapping));
    if (plan) this.set({ plan, step: "review" });
  }

  private async apply(): Promise<void> {
    const api = this.api;
    const plan = this.state.plan;
    if (!api || !plan) return;
    const result = await this.run(() => api.apply(plan.plan_id));
    if (result) this.set({ result, step: "done", undone: false });
  }

  private async undo(snapshotId: string, inWizard: boolean): Promise<void> {
    const api = this.api;
    if (!api) return;
    const result = await this.run(() => api.undo(snapshotId));
    if (!result) return;
    const conflicts = result.conflicts.length
      ? ` Not restored because they were edited afterwards: ${result.conflicts.join(", ")}.`
      : "";
    this.set({
      undone: inWizard ? true : this.state.undone,
      notice: `Restored ${plural(result.restored, "object", "objects")}.${conflicts}`,
    });
    void this.loadOverview();
  }

  // ---- render ---------------------------------------------------------

  private render(): void {
    const s = this.state;
    const nodes: Node[] = [h("style", {}, styles), this.renderToolbar()];
    const content = h("main", { class: "content" });
    if (s.error) content.appendChild(h("div", { class: "notice bad", attrs: { role: "alert" } }, s.error));
    if (s.notice) content.appendChild(h("div", { class: "notice good", attrs: { role: "status" } }, s.notice));

    if (s.loading && !s.overview) {
      content.appendChild(h("div", { class: "spinner" }, "Scanning automations, scripts, scenes and dashboards…"));
    } else if (s.tab === "history") {
      content.appendChild(this.renderHistory());
    } else {
      content.append(this.renderSteps(), this.renderSwap(), this.renderStep());
    }
    nodes.push(content);
    this.root.replaceChildren(...nodes);

    if (this.focusSearch) {
      this.focusSearch = false;
      (this.root.querySelector(".search") as HTMLInputElement | null)?.focus();
    }
  }

  private renderToolbar(): HTMLElement {
    const menu = customElements.get("ha-menu-button")
      ? h("ha-menu-button", { props: { hass: this._hass, narrow: this._narrow } })
      : null;
    const tab = (id: Tab, label: string) =>
      h(
        "button",
        {
          class: "tab",
          attrs: { role: "tab", "aria-selected": String(this.state.tab === id) },
          on: { click: () => this.set({ tab: id, notice: null, error: null }) },
        },
        label,
      );
    return h(
      "header",
      { class: "toolbar" },
      menu,
      h("div", { class: "title" }, "Transplant"),
      h("nav", { class: "tabs", attrs: { role: "tablist" } }, tab("replace", "Replace device"), tab("history", "History")),
    );
  }

  private renderSteps(): HTMLElement {
    const current = STEPS.findIndex((step) => step.id === this.state.step);
    return h(
      "ol",
      { class: "steps", attrs: { "aria-label": "Progress" } },
      STEPS.map((step, i) =>
        h(
          "li",
          {
            class: i === current ? "active" : i < current ? "done" : "",
            attrs: { "aria-current": i === current ? "step" : null },
          },
          step.label,
        ),
      ),
    );
  }

  private renderSwap(): HTMLElement {
    const { oldDevice, newDevice, step } = this.state;
    const slot = (label: string, device: DeviceSummary | null, placeholder: string, current: boolean) =>
      device
        ? h(
            "div",
            { class: `slot${current ? " current" : ""}` },
            h("div", { class: "label" }, label),
            h("div", { class: "name" }, device.name),
            h("div", { class: "meta" }, deviceMeta(device)),
          )
        : h("div", { class: `slot empty${current ? " current" : ""}` }, placeholder);
    return h(
      "section",
      { class: "swap", attrs: { "aria-label": "Device swap" } },
      slot("Replacing", oldDevice, "Pick the device you are replacing", step === "old"),
      h("div", { class: "arrow" }, ARROW()),
      slot("With", newDevice, "Pick its replacement", step === "new"),
    );
  }

  private renderStep(): HTMLElement {
    switch (this.state.step) {
      case "old":
        return this.renderPickOld();
      case "new":
        return this.renderPickNew();
      case "match":
        return this.renderMatch();
      case "review":
        return this.renderReview();
      case "done":
        return this.renderDone();
    }
  }

  private renderDeviceList(devices: DeviceSummary[], onPick: (d: DeviceSummary) => void, hint?: (d: DeviceSummary) => string | null): HTMLElement {
    const query = this.state.query.trim().toLowerCase();
    const filtered = query
      ? devices.filter((d) =>
          [d.name, d.model, d.manufacturer, d.area, d.integration].some((v) => v?.toLowerCase().includes(query)),
        )
      : devices;
    const search = h("input", {
      class: "search",
      attrs: { type: "search", placeholder: "Search by name, model, area or integration", "aria-label": "Search devices" },
      props: { value: this.state.query },
      on: {
        input: (ev) => {
          this.state = { ...this.state, query: (ev.target as HTMLInputElement).value };
          this.focusSearch = true;
          this.render();
          const input = this.root.querySelector(".search") as HTMLInputElement | null;
          if (input) input.setSelectionRange(input.value.length, input.value.length);
        },
      },
    });
    const rows = filtered.slice(0, MAX_ROWS).map((device) =>
      h(
        "button",
        { class: "row", attrs: { type: "button", disabled: this.state.busy }, on: { click: () => onPick(device) } },
        h("div", { class: "main" }, h("div", { class: "name" }, device.name), h("div", { class: "meta" }, deviceMeta(device))),
        hint?.(device) ? h("span", { class: "badge hint" }, hint(device) ?? "") : null,
        device.unavailable ? h("span", { class: "badge offline" }, "Offline") : null,
        h("span", { class: "count" }, device.used_in ? h("strong", {}, `Used in ${device.used_in}`) : "Not used"),
      ),
    );
    const more = filtered.length > MAX_ROWS ? h("div", { class: "empty-note" }, `Showing ${MAX_ROWS} of ${filtered.length}. Refine your search.`) : null;
    const empty = filtered.length === 0 ? h("div", { class: "empty-note" }, "No devices match your search.") : null;
    return h("div", { class: "card" }, search, rows, more, empty);
  }

  private renderPickOld(): HTMLElement {
    const devices = [...(this.state.overview?.devices ?? [])].sort(
      (a, b) => Number(b.unavailable) - Number(a.unavailable) || b.used_in - a.used_in || a.name.localeCompare(b.name),
    );
    const stats = this.state.overview?.stats ?? {};
    const scanned = (["automation", "script", "scene", "dashboard"] as const)
      .filter((t) => stats[t])
      .map((t) => typeLabel(t, stats[t] ?? 0))
      .join(", ");
    return h(
      "section",
      {},
      h("h2", {}, "Which device are you replacing?"),
      h(
        "p",
        { class: "lead" },
        "Transplant moves every automation, script, scene and dashboard from the old device to the new one. You see every change before anything is saved.",
        scanned ? ` Scanned ${scanned}.` : "",
      ),
      this.renderDeviceList(devices, (d) => void this.pickOld(d)),
    );
  }

  private renderPickNew(): HTMLElement {
    const old = this.state.oldDevice;
    if (!old) return h("div");
    const devices = (this.state.overview?.devices ?? [])
      .filter((d) => d.id !== old.id)
      .sort(
        (a, b) =>
          Number(b.area === old.area && !!old.area) - Number(a.area === old.area && !!old.area) ||
          Number(a.unavailable) - Number(b.unavailable) ||
          (b.created_at ?? "").localeCompare(a.created_at ?? ""),
      );
    const hint = (d: DeviceSummary) =>
      d.model && d.model === old.model ? "Same model" : d.area && d.area === old.area ? "Same area" : null;
    return h(
      "section",
      {},
      this.renderUsage(),
      h("h2", {}, "Which device replaces it?"),
      h("p", { class: "lead" }, "Newest devices and devices in the same area are listed first."),
      this.renderDeviceList(devices, (d) => void this.pickNew(d), hint),
      h(
        "div",
        { class: "actions" },
        h("button", { class: "btn", on: { click: () => this.set({ step: "old", oldDevice: null, usage: null, query: "" }) } }, "Back"),
      ),
    );
  }

  private renderUsage(): HTMLElement {
    const items = this.state.usage ?? [];
    if (!items.length) {
      return h("div", { class: "notice warn" }, "This device is not used in any automation, script, scene or dashboard. There is nothing to move.");
    }
    const groups = new Map<string, UsageItem[]>();
    for (const item of items) groups.set(item.source_type, [...(groups.get(item.source_type) ?? []), item]);
    return h(
      "div",
      { class: "card" },
      [...groups.entries()].map(([type, group]) =>
        h(
          "div",
          { class: "usage-group" },
          h("h3", {}, `Used in ${typeLabel(type, group.length)}`),
          h(
            "ul",
            {},
            group.map((item) => h("li", {}, this.objectLink(item.source_type, item.source_id, item.name), item.editable ? "" : " (read-only)")),
          ),
        ),
      ),
    );
  }

  private renderMatch(): HTMLElement {
    const suggestion = this.state.suggestion;
    if (!suggestion) return h("div");
    const newByDomain = new Map<string, typeof suggestion.new_entities>();
    for (const entity of suggestion.new_entities) {
      newByDomain.set(entity.domain, [...(newByDomain.get(entity.domain) ?? []), entity]);
    }
    const confidence = new Map(suggestion.matches.map((m) => [m.old_entity_id, m.confidence]));
    const anyMapped = Object.values(this.state.mapping).some(Boolean);
    const rows = suggestion.old_entities.map((old) => {
      const options = newByDomain.get(old.domain) ?? [];
      const select = h(
        "select",
        {
          attrs: { "aria-label": `Replacement for ${old.name}` },
          on: {
            change: (ev) => {
              const value = (ev.target as HTMLSelectElement).value;
              this.set({ mapping: { ...this.state.mapping, [old.entity_id]: value || null } });
            },
          },
        },
        h("option", { attrs: { value: "" } }, "Keep unchanged"),
        options.map((opt) =>
          h(
            "option",
            { attrs: { value: opt.entity_id, selected: this.state.mapping[old.entity_id] === opt.entity_id } },
            `${opt.name}${opt.state !== null ? ` (${opt.state}${opt.unit ? ` ${opt.unit}` : ""})` : ""}`,
          ),
        ),
      );
      const conf = this.state.mapping[old.entity_id] ? confidence.get(old.entity_id) ?? "low" : "none";
      return h(
        "tr",
        {},
        h("td", {}, h("div", {}, old.name), h("div", { class: "eid" }, old.entity_id)),
        h("td", {}, select),
        h(
          "td",
          { class: "eid" },
          h("span", { class: `conf ${conf}`, attrs: { "aria-hidden": "true" } }),
          conf === "none" ? "—" : `${conf} match`,
        ),
      );
    });
    return h(
      "section",
      {},
      h("h2", {}, "Match old entities to new ones"),
      h("p", { class: "lead" }, "Transplant suggested a match for each entity. Change any that are wrong, or keep an entity unchanged."),
      suggestion.new_entities.length === 0
        ? h("div", { class: "notice warn" }, "The new device has no entities yet. Finish pairing it first, then come back.")
        : null,
      h(
        "div",
        { class: "card" },
        h(
          "table",
          { class: "map" },
          h("thead", {}, h("tr", {}, h("th", {}, "Old entity"), h("th", {}, "Replace with"), h("th", {}, "Match"))),
          h("tbody", {}, rows),
        ),
      ),
      h(
        "div",
        { class: "actions" },
        h("button", { class: "btn", on: { click: () => this.set({ step: "new", newDevice: null, suggestion: null }) } }, "Back"),
        h(
          "button",
          { class: "btn primary", attrs: { disabled: this.state.busy || !anyMapped }, on: { click: () => void this.preview() } },
          "Preview changes",
        ),
      ),
    );
  }

  private renderReview(): HTMLElement {
    const plan = this.state.plan;
    if (!plan) return h("div");
    const { summary } = plan;
    const editable = plan.items.filter((i) => i.editable && i.changes.length);
    const readOnly = plan.items.filter((i) => !i.editable && i.changes.length);
    const reviewNotes = plan.items.flatMap((i) => i.review.map((r) => ({ item: i, ...r })));
    const where = Object.entries(summary.by_type)
      .map(([type, count]) => typeLabel(type, count ?? 0))
      .join(", ");
    return h(
      "section",
      {},
      h("div", { class: "headline" }, summary.replacements ? `${plural(summary.replacements, "replacement", "replacements")} in ${plural(summary.objects, "place", "places")}` : "Nothing to replace"),
      h("p", { class: "lead" }, where ? `Across ${where}. Nothing has been saved yet. Before saving, Transplant keeps a copy so you can undo.` : "None of the editable configuration uses the old entities."),
      reviewNotes.length
        ? h(
            "div",
            { class: "notice warn" },
            h("strong", {}, `${plural(reviewNotes.length, "spot needs", "spots need")} your attention and will stay unchanged:`),
            h("ul", {}, reviewNotes.map((n) => h("li", {}, this.objectLink(n.item.source_type, n.item.source_id, n.item.name), `: ${n.reason}`))),
          )
        : null,
      editable.length ? h("div", { class: "card" }, editable.map((item, i) => this.renderPlanItem(item, i === 0))) : null,
      readOnly.length
        ? h(
            "div",
            { class: "notice warn" },
            h("strong", {}, `${plural(readOnly.length, "object is", "objects are")} defined in YAML and can't be changed automatically:`),
            h("ul", {}, readOnly.map((i) => h("li", {}, i.name, i.read_only_reason ? ` (${i.read_only_reason})` : ""))),
          )
        : null,
      h(
        "div",
        { class: "actions" },
        h("button", { class: "btn", on: { click: () => this.set({ step: "match", plan: null }) } }, "Back"),
        h(
          "button",
          { class: "btn primary", attrs: { disabled: this.state.busy || !summary.objects }, on: { click: () => void this.apply() } },
          summary.objects ? `Replace in ${plural(summary.objects, "place", "places")}` : "Replace",
        ),
      ),
    );
  }

  private renderPlanItem(item: Plan["items"][number], open: boolean): HTMLElement {
    return h(
      "details",
      { class: "item", attrs: { open } },
      h(
        "summary",
        {},
        h("span", { class: "kind" }, item.source_type),
        h("span", { class: "name" }, item.name),
        h("span", { class: "count" }, plural(item.changes.length, "change", "changes")),
      ),
      h(
        "ul",
        { class: "changes" },
        item.changes.map((c) =>
          h(
            "li",
            {},
            h("div", { class: "path" }, c.path, c.kind === "template" ? " (template)" : ""),
            h("div", { class: "diff" }, h("span", { class: "old" }, c.old), h("span", { attrs: { "aria-hidden": "true" } }, "→"), h("span", { class: "new" }, c.new)),
          ),
        ),
      ),
    );
  }

  private renderDone(): HTMLElement {
    const { result, plan, undone } = this.state;
    if (!result || !plan) return h("div");
    const v = result.verification;
    return h(
      "section",
      {},
      h("div", { class: "headline" }, undone ? "Change undone" : `Replaced ${plural(result.replacements, "reference", "references")} in ${plural(result.objects, "place", "places")}`),
      h("p", { class: "lead" }, undone ? "Everything is back the way it was." : "Automations, scripts and scenes were reloaded. Dashboards update the next time they are opened."),
      !undone && v.ok ? h("div", { class: "notice good" }, "Checked: nothing still points to the old device.") : null,
      !undone && !v.ok
        ? h(
            "div",
            { class: "notice warn" },
            h("strong", {}, "Please check these:"),
            h(
              "ul",
              {},
              v.leftovers.map((l) => h("li", {}, `${l.source_id}: ${l.path} still uses an old ID`)),
              v.unavailable.map((e) => h("li", {}, `${e} is unavailable after reload`)),
            ),
          )
        : null,
      !undone
        ? h(
            "div",
            { class: "card" },
            plan.items
              .filter((i) => i.editable && i.changes.length)
              .map((i) => h("div", { class: "row", attrs: { role: "presentation" } }, h("div", { class: "main" }, this.objectLink(i.source_type, i.source_id, i.name)), h("span", { class: "count" }, plural(i.changes.length, "change", "changes")))),
          )
        : null,
      h(
        "div",
        { class: "actions" },
        !undone
          ? h("button", { class: "btn danger", attrs: { disabled: this.state.busy }, on: { click: () => void this.undo(result.snapshot_id, true) } }, "Undo")
          : null,
        h("button", { class: "btn primary", on: { click: () => this.reset() } }, "Replace another device"),
      ),
    );
  }

  private renderHistory(): HTMLElement {
    const snapshots = this.state.overview?.snapshots ?? [];
    return h(
      "section",
      { class: "history" },
      h("h2", {}, "History"),
      h("p", { class: "lead" }, "Every replacement keeps a copy of what it changed. Undo restores objects you haven't edited since."),
      h(
        "div",
        { class: "card" },
        snapshots.length
          ? snapshots.map((snap) =>
              h(
                "div",
                { class: "row" },
                h(
                  "div",
                  { class: "main" },
                  h("div", { class: "name" }, snap.title),
                  h("div", { class: "meta" }, `${new Date(snap.created).toLocaleString(this._hass?.language)}, ${plural(snap.replacements, "replacement", "replacements")} in ${plural(snap.objects, "place", "places")}`),
                ),
                snap.undone
                  ? h("span", { class: "count" }, "Undone")
                  : h("button", { class: "btn danger", attrs: { disabled: this.state.busy }, on: { click: () => void this.undo(snap.id, false) } }, "Undo"),
              ),
            )
          : h("div", { class: "empty-note" }, "No replacements yet. They will show up here."),
      ),
    );
  }

  private objectLink(sourceType: string, sourceId: string, name: string): HTMLElement {
    const path = editorPath(sourceType, sourceId);
    if (!path) return h("span", {}, name);
    return h("a", { attrs: { href: path }, on: { click: (ev) => { ev.preventDefault(); navigate(path); } } }, name);
  }
}

function deviceMeta(device: DeviceSummary): string {
  const model = [device.manufacturer, device.model].filter(Boolean).join(" ");
  return [model, device.area, device.integration].filter(Boolean).join(", ");
}

if (!customElements.get("transplant-panel")) {
  customElements.define("transplant-panel", TransplantPanel);
}
