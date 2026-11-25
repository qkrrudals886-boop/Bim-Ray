export class HvacApi {
  constructor(base) {
    this.base = base.replace(/\/$/, "");
  }
  async _get(path, params = {}) {
    const url = new URL(this.base + path);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
    return res.json();
  }
  groups() { return this._get("/groups"); }
  timerange() { return this._get("/meta/timerange"); }
  state(t) { return this._get("/state", { t }); }
  sensorsByGroup(group, t) { return this._get(`/sensors/${encodeURIComponent(group)}`, { t }); }
  timeseries(code, from, to) { return this._get(`/timeseries/${encodeURIComponent(code)}`, { from, to }); }
}
