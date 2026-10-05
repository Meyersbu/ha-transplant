/** Typed wrapper around Transplant's WebSocket commands. */

export interface HomeAssistant {
  callWS<T>(msg: Record<string, unknown>): Promise<T>;
  language?: string;
  themes?: { darkMode?: boolean };
}

export interface DeviceSummary {
  id: string;
  name: string;
  manufacturer: string | null;
  model: string | null;
  area: string | null;
  integration: string | null;
  entity_count: number;
  unavailable: boolean;
  used_in: number;
  created_at: string | null;
}

export interface SnapshotSummary {
  id: string;
  created: string;
  title: string;
  undone: boolean;
  objects: number;
  replacements: number;
}

export interface Overview {
  devices: DeviceSummary[];
  stats: Record<string, number>;
  warnings: string[];
  snapshots: SnapshotSummary[];
}

export type SourceType = "automation" | "script" | "scene" | "dashboard";

export interface Reference {
  source_type: SourceType;
  source_id: string;
  target_type: "entity" | "device" | "entity_registry_id";
  target_id: string;
  path: string;
  kind: "value" | "key" | "template";
}

export interface UsageItem {
  source_type: SourceType;
  source_id: string;
  name: string;
  entity_id: string | null;
  editable: boolean;
  references: Reference[];
}

export interface EntityDescription {
  entity_id: string;
  name: string;
  domain: string;
  device_class: string | null;
  unit: string | null;
  state: string | null;
}

export interface EntityMatch {
  old_entity_id: string;
  new_entity_id: string | null;
  score: number;
  confidence: "high" | "medium" | "low" | "none";
}

export interface Suggestion {
  matches: EntityMatch[];
  old_entities: EntityDescription[];
  new_entities: EntityDescription[];
}

export interface Change {
  path: string;
  old: string;
  new: string;
  kind: "value" | "key" | "template";
  target_type: string;
}

export interface PlanItem {
  source_type: SourceType;
  source_id: string;
  name: string;
  entity_id: string | null;
  editable: boolean;
  read_only_reason: string | null;
  changes: Change[];
  review: { path: string; reason: string }[];
}

export interface Plan {
  plan_id: string;
  title: string;
  summary: {
    objects: number;
    replacements: number;
    by_type: Partial<Record<SourceType, number>>;
    read_only: number;
    needs_review: number;
  };
  items: PlanItem[];
}

export interface ApplyResult {
  snapshot_id: string;
  objects: number;
  replacements: number;
  verification: {
    ok: boolean;
    leftovers: { source_id: string; path: string }[];
    unavailable: string[];
  };
}

export interface UndoResult {
  restored: number;
  conflicts: string[];
}

export class TransplantApi {
  constructor(private readonly hass: HomeAssistant) {}

  overview(): Promise<Overview> {
    return this.hass.callWS({ type: "transplant/overview" });
  }

  deviceUsage(deviceId: string): Promise<{ device_id: string; items: UsageItem[] }> {
    return this.hass.callWS({ type: "transplant/device_usage", device_id: deviceId });
  }

  suggest(oldDeviceId: string, newDeviceId: string): Promise<Suggestion> {
    return this.hass.callWS({
      type: "transplant/suggest",
      old_device_id: oldDeviceId,
      new_device_id: newDeviceId,
    });
  }

  preview(
    oldDeviceId: string,
    newDeviceId: string,
    entityMap: Record<string, string | null>,
  ): Promise<Plan> {
    return this.hass.callWS({
      type: "transplant/preview",
      old_device_id: oldDeviceId,
      new_device_id: newDeviceId,
      entity_map: entityMap,
    });
  }

  apply(planId: string): Promise<ApplyResult> {
    return this.hass.callWS({ type: "transplant/apply", plan_id: planId });
  }

  undo(snapshotId: string): Promise<UndoResult> {
    return this.hass.callWS({ type: "transplant/undo", snapshot_id: snapshotId });
  }
}

/** Extract a readable message from a WebSocket error. */
export function errorMessage(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return String(err);
}
