/**
 * Minimal DOM builder.
 *
 * All text goes through `textContent`, never `innerHTML`, so entity names,
 * aliases and dashboard titles from user configuration cannot inject markup.
 */

type Child = Node | string | number | null | undefined | false;
type Props = {
  class?: string;
  style?: string;
  on?: Record<string, (ev: Event) => void>;
  attrs?: Record<string, string | boolean | number | null | undefined>;
  props?: Record<string, unknown>;
};

export function h(tag: string, props: Props = {}, ...children: (Child | Child[])[]): HTMLElement {
  const el = document.createElement(tag);
  if (props.class) el.className = props.class;
  if (props.style) el.setAttribute("style", props.style);
  for (const [name, value] of Object.entries(props.attrs ?? {})) {
    if (value === false || value === null || value === undefined) continue;
    el.setAttribute(name, value === true ? "" : String(value));
  }
  for (const [name, value] of Object.entries(props.props ?? {})) {
    (el as unknown as Record<string, unknown>)[name] = value;
  }
  for (const [event, handler] of Object.entries(props.on ?? {})) {
    el.addEventListener(event, handler);
  }
  append(el, children);
  return el;
}

function append(parent: Node, children: (Child | Child[])[]): void {
  for (const child of children) {
    if (Array.isArray(child)) {
      append(parent, child);
    } else if (child === null || child === undefined || child === false) {
      continue;
    } else if (child instanceof Node) {
      parent.appendChild(child);
    } else {
      parent.appendChild(document.createTextNode(String(child)));
    }
  }
}

/** Navigate inside the Home Assistant frontend without a page reload. */
export function navigate(path: string): void {
  history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

const TYPE_LABELS: Record<string, [string, string]> = {
  automation: ["automation", "automations"],
  script: ["script", "scripts"],
  scene: ["scene", "scenes"],
  dashboard: ["dashboard", "dashboards"],
};

export function typeLabel(type: string, count: number): string {
  const [one, many] = TYPE_LABELS[type] ?? [type, `${type}s`];
  return plural(count, one, many);
}

/** Link into the HA editor for an object, if one exists. */
export function editorPath(sourceType: string, sourceId: string): string | null {
  if (sourceId.startsWith("yaml:")) return null;
  switch (sourceType) {
    case "automation":
      return `/config/automation/edit/${encodeURIComponent(sourceId)}`;
    case "script":
      return `/config/script/edit/${encodeURIComponent(sourceId)}`;
    case "scene":
      return `/config/scene/edit/${encodeURIComponent(sourceId)}`;
    case "dashboard":
      return `/${encodeURIComponent(sourceId)}`;
    default:
      return null;
  }
}
