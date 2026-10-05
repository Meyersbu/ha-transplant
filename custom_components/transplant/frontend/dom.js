export function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    if (props.class)
        el.className = props.class;
    if (props.style)
        el.setAttribute("style", props.style);
    for (const [name, value] of Object.entries(props.attrs ?? {})) {
        if (value === false || value === null || value === undefined)
            continue;
        el.setAttribute(name, value === true ? "" : String(value));
    }
    for (const [name, value] of Object.entries(props.props ?? {})) {
        el[name] = value;
    }
    for (const [event, handler] of Object.entries(props.on ?? {})) {
        el.addEventListener(event, handler);
    }
    append(el, children);
    return el;
}
function append(parent, children) {
    for (const child of children) {
        if (Array.isArray(child)) {
            append(parent, child);
        }
        else if (child === null || child === undefined || child === false) {
            continue;
        }
        else if (child instanceof Node) {
            parent.appendChild(child);
        }
        else {
            parent.appendChild(document.createTextNode(String(child)));
        }
    }
}
export function navigate(path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}
export function plural(count, one, many) {
    return `${count} ${count === 1 ? one : many}`;
}
const TYPE_LABELS = {
    automation: ["automation", "automations"],
    script: ["script", "scripts"],
    scene: ["scene", "scenes"],
    dashboard: ["dashboard", "dashboards"],
};
export function typeLabel(type, count) {
    const [one, many] = TYPE_LABELS[type] ?? [type, `${type}s`];
    return plural(count, one, many);
}
export function editorPath(sourceType, sourceId) {
    if (sourceId.startsWith("yaml:"))
        return null;
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
