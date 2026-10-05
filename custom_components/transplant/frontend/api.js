export class TransplantApi {
    constructor(hass) {
        this.hass = hass;
    }
    overview() {
        return this.hass.callWS({ type: "transplant/overview" });
    }
    deviceUsage(deviceId) {
        return this.hass.callWS({ type: "transplant/device_usage", device_id: deviceId });
    }
    suggest(oldDeviceId, newDeviceId) {
        return this.hass.callWS({
            type: "transplant/suggest",
            old_device_id: oldDeviceId,
            new_device_id: newDeviceId,
        });
    }
    preview(oldDeviceId, newDeviceId, entityMap) {
        return this.hass.callWS({
            type: "transplant/preview",
            old_device_id: oldDeviceId,
            new_device_id: newDeviceId,
            entity_map: entityMap,
        });
    }
    apply(planId) {
        return this.hass.callWS({ type: "transplant/apply", plan_id: planId });
    }
    undo(snapshotId) {
        return this.hass.callWS({ type: "transplant/undo", snapshot_id: snapshotId });
    }
}
export function errorMessage(err) {
    if (err && typeof err === "object" && "message" in err) {
        return String(err.message);
    }
    return String(err);
}
