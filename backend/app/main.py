"""MineWatch dashboard API (FastAPI).

Serves:
  /api/...      JSON API over the precomputed case bundle (data/cases.json) + SQLite review store
  /assets/...   imagery / overlays produced by pipeline/build_data.py
  /             the built React frontend (frontend/dist), SPA fallback

Run:  .venv/bin/uvicorn backend.app.main:app --port 8000      (from the project root)
"""
import html
import json
import os
from datetime import datetime, timezone
from typing import Optional

import geopandas as gpd
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pyproj import Geod
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

from .store import Store, now_iso

GEOD = Geod(ellps="WGS84")
ADMIN_SEED_USER = os.environ.get("MINEWATCH_ADMIN_USER", "superadmin")
ADMIN_SEED_PASS = os.environ.get("MINEWATCH_ADMIN_PASS", "L9XxruwgeyESht")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.environ.get("MINEWATCH_DATA", os.path.join(ROOT, "data"))
DIST = os.path.join(ROOT, "frontend", "dist")

# ------------------------------------------------------------------ status rule ----
# The repo has NO agreed threshold for permit categories yet (context.md: "needs a product
# decision"). This dashboard uses a PROVISIONAL, configurable rule and shows it in the UI.
#   plurality : whichever share of the disturbed area is largest wins
#               (no permit -> HIGH, expired permit -> MEDIUM, active permit -> LOW)
#   strict    : HIGH if pct outside permits >= MINEWATCH_HIGH_PCT, else MEDIUM if any
#               expired-permit overlap, else LOW
STATUS_RULE = os.environ.get("MINEWATCH_STATUS_RULE", "plurality")
HIGH_PCT = float(os.environ.get("MINEWATCH_HIGH_PCT", os.environ.get("MINEWATCH_MERAH_PCT", "50")))

PERMIT_CATEGORY_LABELS = {
    "HIGH": "No Matching Permit",
    "MEDIUM": "Permit Expired",
    "LOW": "Inside Valid Permit",
    "UNCHECKED": "Not Assessed",
}

DECISIONS = {
    "confirmed": "Confirmed illegal",
    "verify": "Needs field verification",
    "fp": "False positive",
    "legal": "Legal",
}
ALERTING = {"confirmed", "verify"}
RECALL_WINDOW_S = 600


def status_rule_text():
    if STATUS_RULE == "strict":
        return (f"Provisional rule: No Matching Permit if at least {HIGH_PCT:g}% of the detected area lies outside all mapped permits; "
                "otherwise Permit Expired if there is any expired overlap, or Inside Valid Permit as the fallback.")
    return ("Provisional rule: the category follows the largest share of the detected area — "
            "outside mapped permits, overlapping expired permits, or overlapping active permits.")


def classify(cc):
    if not cc:
        return "UNCHECKED"
    a, e, n = cc["in_active_ha"], cc["in_expired_ha"], cc["no_permit_ha"]
    if STATUS_RULE == "strict":
        if cc["pct_outside_permits"] >= HIGH_PCT:
            return "HIGH"
        return "MEDIUM" if e > 0 else "LOW"
    # Preserve the original tie-break: no match, then expired, then active.
    best = max(((n, "HIGH"), (e, "MEDIUM"), (a, "LOW")), key=lambda pair: pair[0])
    return best[1]


# ------------------------------------------------------------------------ data ----
def load_bundle():
    with open(os.path.join(DATA, "cases.json")) as f:
        b = json.load(f)
    for c in b["cases"]:
        c["status"] = classify(c["crosscheck"])
    return b


BUNDLE = load_bundle()
CASES = {c["id"]: c for c in BUNDLE["cases"]}
ORDER = [c["id"] for c in BUNDLE["cases"]]
STORE = Store(os.path.join(DATA, "runtime", "minewatch.db"))
STORE.seed_user(os.environ.get("MINEWATCH_SEED_USER", "admin"), os.environ.get("MINEWATCH_SEED_PASS", "admin"))
STORE.seed_user(ADMIN_SEED_USER, ADMIN_SEED_PASS, role="Admin")
SESSION_COOKIE = "mw_session"
_PERMITS: Optional[gpd.GeoDataFrame] = None
CROSSCHECK_RADIUS_KM = 3.0


def permits_path():
    return os.path.join(DATA, "permits.geojson")


def reset_permits_cache():
    global _PERMITS
    _PERMITS = None


def permits_gdf():
    global _PERMITS
    if _PERMITS is None:
        g = gpd.read_file(permits_path())
        if "valid_until" in g.columns:  # GDAL may parse ISO dates into Timestamps
            g["valid_until"] = g["valid_until"].map(
                lambda v: None if v is None or v != v else (v.date().isoformat() if hasattr(v, "date") else str(v)[:10]))
        if "admin_added" not in g.columns:
            g["admin_added"] = False
        g["admin_added"] = g["admin_added"].fillna(False).astype(bool)
        g.sindex
        _PERMITS = g
    return _PERMITS


def save_permits(g):
    g.to_file(permits_path(), driver="GeoJSON")
    reset_permits_cache()


def next_objectid(g):
    if g.empty or g["objectid"].isna().all():
        return 1
    return int(pd.to_numeric(g["objectid"], errors="coerce").max()) + 1


def geom_from_input(geojson=None, polygon=None):
    """geojson: a parsed GeoJSON Feature/FeatureCollection/Geometry dict (uploaded file,
    parsed client-side). polygon: [[lat, lon], ...] vertices from the Leaflet draw tool."""
    if geojson:
        gj = geojson
        if gj.get("type") == "FeatureCollection":
            feats = gj.get("features") or []
            if not feats:
                raise HTTPException(422, "uploaded file has no features")
            geom = shape(feats[0]["geometry"])
        elif gj.get("type") == "Feature":
            geom = shape(gj["geometry"])
        else:
            geom = shape(gj)
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise HTTPException(422, "uploaded geometry must be a Polygon or MultiPolygon")
        return geom
    if polygon and len(polygon) >= 3:
        return Polygon([(pt[1], pt[0]) for pt in polygon])  # Leaflet gives [lat, lon]
    return None


def _geo_area_ha(geom):
    if geom is None or geom.is_empty:
        return 0.0
    a, _ = GEOD.geometry_area_perimeter(geom)
    return abs(a) / 10000.0


def _geo_dist_km(pt_a, pt_b):
    _, _, d = GEOD.inv(pt_a.x, pt_a.y, pt_b.x, pt_b.y)
    return abs(d) / 1000.0


def save_bundle():
    with open(os.path.join(DATA, "cases.json"), "w") as f:
        json.dump(BUNDLE, f)


def recrosscheck_case(c, permits):
    """Re-derive c['crosscheck'] from the case's already-detected disturbance polygons
    (data/assets/<slug>/disturbance.geojson, produced once by the model pipeline) against
    the CURRENT permits table. No model inference needed -- only the permit overlap changes."""
    path = os.path.join(DATA, "assets", c["slug"], "disturbance.geojson")
    if not os.path.exists(path):
        return False
    dist = gpd.read_file(path)
    if dist.crs and str(dist.crs).upper() != "EPSG:4326":
        dist = dist.to_crs("EPSG:4326")
    dist = dist[~dist.geometry.is_empty & dist.geometry.notna()]
    if dist.empty:
        return False
    union = dist.geometry.union_all()
    total_ha = sum(_geo_area_ha(g) for g in dist.geometry)
    if total_ha <= 0:
        return False
    radius_km = (c.get("crosscheck") or {}).get("radius_km", CROSSCHECK_RADIUS_KM)
    buf = radius_km / 111.0
    minx, miny, maxx, maxy = union.bounds
    cand = permits.iloc[list(permits.sindex.query(box(minx - buf, miny - buf, maxx + buf, maxy + buf), predicate="intersects"))]
    ref_pt = union.centroid
    ref_date = c["imagery"]["after_date"][:10]
    rows, active_parts, expired_parts = [], [], []
    for _, r in cand.iterrows():
        inter = union.intersection(r.geometry)
        ov = _geo_area_ha(inter) if not inter.is_empty else 0.0
        dcent = _geo_dist_km(ref_pt, r.geometry.centroid)
        if ov <= 0.01 and dcent > radius_km:
            continue
        end = r.get("valid_until")
        state = "unknown" if not end else ("active" if end >= ref_date else "expired")
        rec = {
            "objectid": int(r["objectid"]), "name": r.get("name") or "(name not recorded)",
            "sk": r.get("skblok") or "-", "type": r.get("tiptmb") or "-", "commodity": r.get("commodity") or "-",
            "issuer": "-", "status_code": None, "valid_from": None, "valid_until": end, "state": state,
            "area_ha": round(_geo_area_ha(r.geometry), 1), "distance_km": round(dcent, 2),
            "overlap_ha": round(ov, 2), "pct_of_disturbance": round(ov / total_ha * 100, 1) if total_ha else 0,
        }
        rows.append(rec)
        if ov > 0:
            (active_parts if state == "active" else expired_parts).append(inter)
    rows.sort(key=lambda x: (-(x["overlap_ha"] or 0), x["distance_km"]))
    active_u = unary_union(active_parts) if active_parts else None
    expired_u = unary_union(expired_parts) if expired_parts else None
    if expired_u is not None and active_u is not None:
        expired_u = expired_u.difference(active_u)
    in_active = _geo_area_ha(active_u) if active_u is not None and not active_u.is_empty else 0.0
    in_expired = _geo_area_ha(expired_u) if expired_u is not None and not expired_u.is_empty else 0.0
    outside = max(total_ha - in_active - in_expired, 0.0)
    cc = dict(c.get("crosscheck") or {})
    cc.update({
        "method": cc.get("method") or "FC-Siam-diff v4 model vs BIG KSP permit polygons (re-cross-checked after an Admin permit edit).",
        "radius_km": radius_km, "disturbed_area_ha": round(total_ha, 1),
        "overlap_with_permits_ha": round(in_active + in_expired, 1), "outside_permits_ha": round(outside, 1),
        "pct_outside_permits": round(outside / total_ha * 100, 1) if total_ha else 0.0,
        "n_permits_found_nearby": len(rows), "in_active_ha": round(in_active, 1),
        "in_expired_ha": round(in_expired, 1), "no_permit_ha": round(outside, 1),
        "validity_reference_date": ref_date, "permits": rows,
        "polygon_source": cc.get("polygon_source") or "dashboard pipeline",
    })
    c["crosscheck"] = cc
    c["status"] = classify(cc)
    return True


def recrosscheck_all():
    permits = permits_gdf()
    n = sum(1 for c in CASES.values() if recrosscheck_case(c, permits))
    save_bundle()
    return n


def review_state(cid, dec=None, asg=None):
    """dec/asg: None = look up; {} = known to be absent."""
    dec = dec if dec is not None else STORE.active_decision(cid)
    asg = asg if asg is not None else STORE.assignment(cid)
    return {
        "decision": dec["decision"] if dec else None,
        "decision_label": DECISIONS.get(dec["decision"]) if dec else None,
        "decided_by": dec["actor"] if dec else None,
        "decided_at": dec["created_at"] if dec else None,
        "assignee": asg["assignee"] if asg else None,
    }


def summary(c, dec=None, asg=None):
    cc = c["crosscheck"]
    return {
        "id": c["id"], "slug": c["slug"], "loc": c["loc"], "kab": c["kab"], "prov": c["prov"], "com": c["com"],
        "lat": c["lat"], "lon": c["lon"], "status": c["status"], "quality": c["quality"],
        "quality_label": c["quality_label"],
        "before_date": c["imagery"]["before_date"], "after_date": c["imagery"]["after_date"],
        "sharp_loss": c["ndvi"]["sharp_ndvi_loss_pixel_fraction"] if "ndvi" in c
                      else c["imagery"].get("model_flagged_pixel_fraction"),
        "area_ha": cc["disturbed_area_ha"] if cc else None,
        "pct_outside": cc["pct_outside_permits"] if cc else None,
        "outside_ha": cc["outside_permits_ha"] if cc else None,
        "in_active_ha": cc["in_active_ha"] if cc else None,
        "in_expired_ha": cc["in_expired_ha"] if cc else None,
        "no_permit_ha": cc["no_permit_ha"] if cc else None,
        "gt_area_ha": c["gt_area_ha"],
        "operators": [p["name"] for p in (cc["permits"] if cc else []) if (p["overlap_ha"] or 0) > 0][:3],
        "permit_nos": [p["sk"] for p in (cc["permits"] if cc else c["nearby_permits"])],
        "thumbs": [c["assets"]["thumb_before"], c["assets"]["thumb_after"]],
        "review": review_state(c["id"], dec, asg),
    }


def get_case(cid):
    c = CASES.get(cid)
    if not c:
        raise HTTPException(404, f"unknown case {cid}")
    return c


# ------------------------------------------------------------------------- app ----
app = FastAPI(title="MineWatch dashboard API", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

# -------------------------------------------------------------------------- auth ----
# Single login gate in front of everything that isn't the public landing/login page
# or the login API itself. No roles yet — one shared account is enough for the pilot.
AUTH_OPEN_API = {"/api/health"}


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    request.state.user = STORE.session_user(request.cookies.get(SESSION_COOKIE))
    if path.startswith("/api/auth/") or path in AUTH_OPEN_API:
        return await call_next(request)
    if not request.state.user:
        if path.startswith("/app"):
            return RedirectResponse("/login", status_code=307)
        if path.startswith("/api/") or path.startswith("/assets/"):
            return JSONResponse({"detail": "login required"}, status_code=401)
    return await call_next(request)


def require_user(request: Request) -> str:
    """Dependency for endpoints that need the authenticated username (middleware already
    blocked the request if it's missing, but mypy/readability likes an explicit check)."""
    if not request.state.user:
        raise HTTPException(401, "login required")
    return request.state.user


def require_admin(request: Request) -> str:
    if not request.state.user:
        raise HTTPException(401, "login required")
    if (STORE.role_of(request.state.user) or "Analyst") != "Admin":
        raise HTTPException(403, "this section is limited to Admin accounts")
    return request.state.user


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


@app.post("/api/auth/login")
def login(body: LoginIn):
    username = body.username.strip()
    if not STORE.check_password(username, body.password):
        raise HTTPException(401, "invalid username or password")
    STORE.touch_login(username)
    token = STORE.create_session(username)
    resp = JSONResponse({"username": username, "role": STORE.role_of(username) or "Analyst"})
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=12 * 3600, path="/")
    return resp


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        STORE.delete_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def me(request: Request):
    if not request.state.user:
        raise HTTPException(401, "login required")
    return {"username": request.state.user, "role": STORE.role_of(request.state.user) or "Analyst"}


@app.get("/api/health")
def health():
    return {"ok": True, "cases": len(CASES), "generated_at": BUNDLE["meta"]["generated_at"]}


@app.get("/api/meta")
def meta():
    m = dict(BUNDLE["meta"])
    m.update({
        "status_rule": STATUS_RULE, "status_rule_text": status_rule_text(),
        "decisions": DECISIONS,
        "alerting": "MOCK — alert integration to DLHK/Polda is not built; nothing is sent.",
        "latest_after_date": max(c["imagery"]["after_date"] for c in CASES.values()),
    })
    return m


@app.get("/api/cases")
def list_cases():
    decs, asgs = STORE.all_active_decisions(), STORE.all_assignments()
    return [summary(CASES[i], decs.get(i, {}), asgs.get(i, {})) for i in ORDER]


@app.get("/api/cases/{cid}")
def case_detail(cid: str, request: Request, log: bool = False):
    c = get_case(cid)
    if log:
        STORE.log_view(cid, request.state.user)
    idx = ORDER.index(cid)
    out = dict(c)
    dec = STORE.active_decision(cid)
    out.update({
        "review": review_state(cid),
        "active_decision": dec,
        "audit": STORE.audit(cid),
        "viewers": STORE.viewers(cid),
        "prev_id": ORDER[idx - 1] if idx > 0 else None,
        "next_id": ORDER[idx + 1] if idx < len(ORDER) - 1 else None,
        "status_rule_text": status_rule_text(),
    })
    return out


class DecisionIn(BaseModel):
    decision: str
    notes: str = Field("", max_length=4000)
    ack: bool


@app.post("/api/cases/{cid}/decision")
def post_decision(cid: str, body: DecisionIn, user: str = Depends(require_user)):
    c = get_case(cid)
    if body.decision not in DECISIONS:
        raise HTTPException(422, "unknown decision")
    if not body.ack:
        raise HTTPException(422, "evidence acknowledgement is required")
    if STORE.active_decision(cid):
        raise HTTPException(409, "case already has an active decision; recall it first")
    alerting = body.decision in ALERTING
    ref = f"{'ALR' if alerting else 'CLS'}-{datetime.now(timezone.utc):%Y%m%d}-{STORE.next_ref_seq():04d}"
    dec = STORE.add_decision(cid, body.decision, body.notes.strip(), user, ref,
                             "mock_alert" if alerting else "closed")
    STORE.log(cid, "decision", user,
              f"{DECISIONS[body.decision]} · {ref}" + (" · alert MOCK (not sent)" if alerting else " · closed internally"))
    return {"decision": dec, "review": review_state(cid), "recipients": recipients(c) if alerting else []}


@app.post("/api/cases/{cid}/recall")
def post_recall(cid: str, user: str = Depends(require_user)):
    get_case(cid)
    dec = STORE.active_decision(cid)
    if not dec:
        raise HTTPException(404, "no active decision")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(dec["created_at"])).total_seconds()
    if age > RECALL_WINDOW_S:
        raise HTTPException(409, "recall window (10 min) has passed")
    STORE.recall(dec["id"])
    STORE.log(cid, "recalled", user, dec["ref"])
    return {"review": review_state(cid)}


class AssignIn(BaseModel):
    assignee: str = Field(..., min_length=1, max_length=80)


@app.post("/api/cases/{cid}/assign")
def post_assign(cid: str, body: AssignIn, user: str = Depends(require_user)):
    get_case(cid)
    STORE.set_assignment(cid, body.assignee.strip(), user)
    STORE.log(cid, "assigned", user, body.assignee.strip())
    return {"review": review_state(cid)}


def recipients(c):
    p = c["prov"]
    return [f"DLHK Provinsi {p}", f"Polda {p} · Ditreskrimsus", f"Dinas ESDM Provinsi {p} (cc)"]


@app.get("/api/permits")
def permits_in_bbox(bbox: str = Query(..., description="west,south,east,north"), limit: int = 1500):
    try:
        w, s, e, n = [float(x) for x in bbox.split(",")]
    except ValueError:
        raise HTTPException(422, "bbox must be west,south,east,north")
    if (e - w) * (n - s) > 400:  # roughly > 20x20 degrees: refuse national dumps
        raise HTTPException(422, "bbox too large; zoom in")
    g = permits_gdf()
    idx = list(g.sindex.query(box(w, s, e, n), predicate="intersects"))[:limit]
    sub = g.iloc[idx]
    feats = [{"type": "Feature", "geometry": mapping(r.geometry),
              "properties": {k: (None if (isinstance(r[k], float) and r[k] != r[k]) else r[k])
                             for k in ("objectid", "name", "commodity", "valid_until", "prov", "kab", "tiptmb", "skblok")}}
             for _, r in sub.iterrows()]
    return {"type": "FeatureCollection", "features": feats, "truncated": len(idx) >= limit}


@app.get("/api/permits/all")
def permits_all():
    """National permit layer (4,608 polygons, simplified ~50 m) for the overview map."""
    return FileResponse(os.path.join(DATA, "permits.geojson"), media_type="application/geo+json")


@app.get("/api/permits/search")
def permits_search(q: str = "", prov: str = "", page: int = 1, size: int = 50):
    g = permits_gdf()
    df = g.drop(columns="geometry")
    if q:
        ql = q.lower()
        m = (df["name"].fillna("").str.lower().str.contains(ql, regex=False)
             | df["skblok"].fillna("").str.lower().str.contains(ql, regex=False)
             | df["kab"].fillna("").str.lower().str.contains(ql, regex=False)
             | df["commodity"].fillna("").str.lower().str.contains(ql, regex=False))
        df = df[m]
    if prov:
        df = df[df["prov"] == prov]
    total = len(df)
    size = max(1, min(size, 200))
    rows = df.sort_values("name").iloc[(page - 1) * size: page * size]
    today = datetime.now(timezone.utc).date().isoformat()
    items = []
    for _, r in rows.iterrows():
        d = {k: (None if (isinstance(r[k], float) and r[k] != r[k]) else r[k]) for k in
             ("objectid", "name", "commodity", "valid_until", "prov", "kab", "tiptmb", "skblok")}
        d["state_today"] = None if not d["valid_until"] else ("active" if d["valid_until"] >= today else "expired")
        items.append(d)
    provs = sorted(p for p in g["prov"].dropna().unique())
    return {"total": total, "page": page, "size": size, "items": items, "provinces": provs}


@app.get("/api/permits/{objectid}")
def permit_detail(objectid: int, user: str = Depends(require_user)):
    g = permits_gdf()
    mask = g["objectid"] == objectid
    if not mask.any():
        raise HTTPException(404, "unknown permit")
    r = g[mask].iloc[0]
    today = datetime.now(timezone.utc).date().isoformat()
    end = r.get("valid_until")
    cen = r.geometry.centroid
    minx, miny, maxx, maxy = r.geometry.bounds
    return {
        "objectid": int(r["objectid"]), "name": r.get("name") or "(name not recorded)",
        "skblok": r.get("skblok") or None, "kab": r.get("kab") or None, "prov": r.get("prov") or None,
        "tiptmb": r.get("tiptmb") or None, "commodity": r.get("commodity") or None,
        "valid_until": end, "state_today": None if not end else ("active" if end >= today else "expired"),
        "area_ha": round(_geo_area_ha(r.geometry), 1),
        "centroid": {"lat": round(float(cen.y), 5), "lon": round(float(cen.x), 5)},
        "bbox": [round(float(v), 5) for v in (minx, miny, maxx, maxy)],
        "admin_added": bool(r.get("admin_added", False)),
        "geometry": mapping(r.geometry),
    }


@app.get("/api/export.geojson")
def export_geojson():
    decs, asgs = STORE.all_active_decisions(), STORE.all_assignments()
    feats = []
    for i in ORDER:
        c = CASES[i]
        s = summary(c, decs.get(i, {}), asgs.get(i, {}))
        props = {k: v for k, v in s.items() if k not in ("thumbs", "lat", "lon")}
        props["detection_method"] = BUNDLE["meta"]["detection_method"]
        props["note"] = "Flagged for review — not an automatic legal verdict."
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                      "properties": props})
    body = {"type": "FeatureCollection", "features": feats,
            "metadata": {"generated_at": now_iso(), "status_rule": status_rule_text(),
                         "permit_baseline": BUNDLE["meta"]["permit_baseline"]}}
    return JSONResponse(body, headers={"Content-Disposition": 'attachment; filename="minewatch_cases.geojson"'})


@app.get("/api/cases/{cid}/report", response_class=HTMLResponse)
def case_report(cid: str):
    c = get_case(cid)
    e = html.escape
    cc = c["crosscheck"]
    dec = STORE.active_decision(cid)
    n = c.get("ndvi")
    rows = cc["permits"] if cc else c["nearby_permits"]
    prow = "".join(
        f"<tr><td>{e(p['name'])}<br><small>{e(p['sk'])} · {e(p['type'])} · {e(str(p['commodity']))}</small></td>"
        f"<td>{e(p['state'])}</td><td>{e(p['valid_until'] or '—')}</td><td>{p['distance_km']} km</td>"
        f"<td>{'' if p['overlap_ha'] is None else p['overlap_ha']}</td></tr>" for p in rows) or \
        "<tr><td colspan=5>No permit polygon found in the search radius.</td></tr>"
    cc_html = (f"<p>Disturbed area (≤{cc['radius_km']:g} km of case point): <b>{cc['disturbed_area_ha']} ha</b> · "
               f"inside active permit {cc['in_active_ha']} ha · inside expired permit {cc['in_expired_ha']} ha · "
               f"no permit {cc['no_permit_ha']} ha ({cc['pct_outside_permits']}% outside any permit).</p>"
               if cc else "<p><b>Permit cross-check not run for this case</b> (no disturbance polygons yet). "
                          f"Table lists permits within {c['nearby_radius_km']:g} km of the reference point.</p>")
    dec_html = (f"<p>Decision: <b>{e(DECISIONS[dec['decision']])}</b> by {e(dec['actor'])} at {e(dec['created_at'])} "
                f"(ref {e(dec['ref'])}).</p><p>Notes: {e(dec['notes']) or '—'}</p>"
                if dec else "<p><b>No analyst decision recorded yet.</b></p>")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(c['id'])} — MineWatch case report</title>
<style>body{{font:13px/1.45 Inter,system-ui,sans-serif;color:#17181A;max-width:860px;margin:24px auto;padding:0 20px}}
h1{{font-size:20px;margin:0}}h2{{font-size:12px;letter-spacing:.08em;color:#5F6368;margin:22px 0 6px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #E2E2DE;padding:6px;text-align:left;vertical-align:top}}
.imgs{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.imgs img{{width:100%}}.warn{{border:1.5px solid #17181A;padding:8px 10px;margin:12px 0}}
small{{color:#5F6368}}@media print{{.noprint{{display:none}}}}</style></head><body>
<p class="noprint"><button onclick="window.print()">Print / save as PDF</button></p>
<small>MineWatch · case report · generated {e(now_iso())}</small>
<h1>{e(c['id'])} · {e(c['loc'])}</h1><p>{e(c['kab'])}, {e(c['prov'])} · commodity {e(c['com'])} · permit category <b>{e(PERMIT_CATEGORY_LABELS[c['status']])}</b></p>
<div class="warn">Flagged for review — not an automatic legal verdict. Detection is {"an NDVI threshold (not an AI model)" if n else "the FC-Siam-diff v4 AI model (checkpoint production_v4_base64_reg_jasansky, threshold 0.5) — NOT NDVI"}.
Permit data is the BIG KSP ~2022 baseline, not real-time. {e(status_rule_text())}</div>
<h2>IMAGERY · BEFORE {e(c['imagery']['before_date'])} / AFTER {e(c['imagery']['after_date'])}</h2>
<div class="imgs"><img src="{c['assets']['before']}"><img src="{c['assets']['after']}"></div>
{f'''<h2>NDVI / NDMI</h2><p>Sharp NDVI loss (&Delta;NDVI &lt; &minus;0.2): <b>{n["sharp_ndvi_loss_pixel_fraction"]*100:.1f}%</b> of frame pixels &middot;
mean NDVI {n["before"]["ndvi_mean"]:.3f} &rarr; {n["after"]["ndvi_mean"]:.3f} &middot; mean NDMI {n["before"]["ndmi_mean"]:.3f} &rarr; {n["after"]["ndmi_mean"]:.3f}</p>''' if n else
 f'''<h2>AI MODEL DETECTION</h2><p>Pixels flagged as changed by the model: <b>{c["imagery"].get("model_flagged_pixel_fraction", 0)*100:.1f}%</b> of frame pixels (threshold 0.5).</p>'''}
<p>Data quality: {e(c['quality_label'])} — {e(c['quality_note'])}{(' ' + e(c['recheck_note'])) if c.get('recheck_note') else ''}</p>
<h2>PERMIT CROSS-CHECK</h2>{cc_html}<table><tr><th>Permit</th><th>State</th><th>Valid until</th><th>Distance</th><th>Overlap (ha)</th></tr>{prow}</table>
<h2>GROUND-TRUTH REFERENCE</h2><p>{e(c['gt_status'])}<br><small>Sources: {e(', '.join(c['sources']))} · location precision: {e(c['loc_precision'])}</small></p>
<h2>ANALYST REVIEW</h2>{dec_html}
</body></html>"""
    return HTMLResponse(page)


# --------------------------------------------------------------------- admin ----
class UserIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-z0-9._-]+$")
    password: str = Field(..., min_length=8, max_length=200)
    role: str = Field("Analyst")


class PasswordIn(BaseModel):
    password: str = Field(..., min_length=8, max_length=200)


class PermitIn(BaseModel):
    no: str = ""
    holder: str = Field(..., min_length=1, max_length=200)
    commodity: str = ""
    type: str = "IUP"
    status: str = "active"
    expiry: Optional[str] = None
    prov: str = ""
    kab: str = ""
    geojson: Optional[dict] = None
    polygon: Optional[list] = None


@app.get("/api/admin/users")
def admin_list_users(user: str = Depends(require_admin)):
    return {"users": STORE.list_users(), "admin_count": STORE.count_admins(), "me": user}


@app.post("/api/admin/users")
def admin_add_user(body: UserIn, user: str = Depends(require_admin)):
    if body.role not in ("Admin", "Analyst"):
        raise HTTPException(422, "role must be Admin or Analyst")
    uname = body.username.strip().lower()
    try:
        STORE.create_user(uname, body.password, body.role)
    except ValueError as e:
        raise HTTPException(409, str(e))
    STORE.admin_log_add(user, f"Added user {uname}", f"Role {body.role}")
    return {"ok": True}


@app.post("/api/admin/users/{username}/reset-password")
def admin_reset_password(username: str, body: PasswordIn, user: str = Depends(require_admin)):
    if not STORE.get_user(username):
        raise HTTPException(404, "unknown user")
    STORE.set_password(username, body.password)
    STORE.admin_log_add(user, f"Reset password for {username}", "Temporary password set")
    return {"ok": True}


@app.delete("/api/admin/users/{username}")
def admin_delete_user(username: str, user: str = Depends(require_admin)):
    target = STORE.get_user(username)
    if not target:
        raise HTTPException(404, "unknown user")
    if target["role"] == "Admin" and STORE.count_admins() <= 1:
        raise HTTPException(409, "can't delete the last remaining Admin account")
    stats = next((u for u in STORE.list_users() if u["username"] == username), {})
    STORE.delete_user(username)
    STORE.admin_log_add(user, f"Deleted user {username}",
                        f"{stats.get('decisions_signed', 0)} signed decisions and {stats.get('audit_entries', 0)} audit entries kept in history")
    return {"ok": True}


@app.get("/api/admin/permits")
def admin_list_permits(q: str = "", commodity: str = "", type: str = "", status: str = "",
                        page: int = 1, size: int = 50, user: str = Depends(require_admin)):
    g = permits_gdf()
    df = g
    if q:
        ql = q.lower()
        m = (df["name"].fillna("").str.lower().str.contains(ql, regex=False)
             | df["skblok"].fillna("").str.lower().str.contains(ql, regex=False)
             | df["prov"].fillna("").str.lower().str.contains(ql, regex=False))
        df = df[m]
    if commodity:
        df = df[df["commodity"] == commodity]
    if type:
        df = df[df["tiptmb"] == type]
    today = datetime.now(timezone.utc).date().isoformat()
    if status in ("active", "expired"):
        is_active = df["valid_until"].fillna("9999-99-99") >= today
        df = df[is_active] if status == "active" else df[~is_active]
    total = len(df)
    size = max(1, min(size, 200))
    rows = df.sort_values("objectid", ascending=False).iloc[(page - 1) * size: page * size]
    items = []
    for _, r in rows.iterrows():
        end = r.get("valid_until")
        active = bool(end) and end >= today
        items.append({
            "objectid": int(r["objectid"]), "no": r.get("skblok") or f"OBJ-{int(r['objectid'])}",
            "holder": r.get("name") or "(name not recorded)", "commodity": r.get("commodity") or "-",
            "type": r.get("tiptmb") or "-", "status": "active" if active else ("expired" if end else "unknown"),
            "valid_until": end, "prov": r.get("prov") or "-", "kab": r.get("kab") or "-",
            "area_ha": round(_geo_area_ha(r.geometry), 1), "added": bool(r.get("admin_added", False)),
        })
    return {"total": total, "page": page, "size": size, "items": items,
            "provinces": sorted(p for p in g["prov"].dropna().unique()),
            "types": sorted(t for t in g["tiptmb"].dropna().unique()),
            "commodities": sorted(c for c in g["commodity"].dropna().unique()),
            "admin_added_count": int(g["admin_added"].sum())}


@app.post("/api/admin/permits")
def admin_add_permit(body: PermitIn, user: str = Depends(require_admin)):
    geom = geom_from_input(body.geojson, body.polygon)
    if geom is None:
        raise HTTPException(422, "add a location: upload a GeoJSON polygon, or draw at least 3 vertices on the map")
    g = permits_gdf()
    oid = next_objectid(g)
    new_row = gpd.GeoDataFrame([{
        "objectid": oid, "name": body.holder.strip(), "commodity": body.commodity, "tiptmb": body.type,
        "skblok": body.no.strip() or None, "valid_until": body.expiry or None,
        "prov": body.prov or None, "kab": body.kab or None, "admin_added": True, "geometry": geom,
    }], crs=g.crs or "EPSG:4326")
    merged = gpd.GeoDataFrame(pd.concat([g, new_row], ignore_index=True), crs=g.crs or "EPSG:4326")
    save_permits(merged)
    n = recrosscheck_all()
    STORE.admin_log_add(user, f"Added permit OBJ-{oid}",
                        f"{body.holder.strip()} · {body.commodity} · {body.type} · {body.prov or '—'} · geometry "
                        + ("from upload" if body.geojson else f"drawn ({len(body.polygon)} vertices)"))
    return {"ok": True, "objectid": oid, "cases_recrosschecked": n}


@app.put("/api/admin/permits/{objectid}")
def admin_edit_permit(objectid: int, body: PermitIn, user: str = Depends(require_admin)):
    g = permits_gdf()
    mask = g["objectid"] == objectid
    if not mask.any():
        raise HTTPException(404, "unknown permit")
    idx = g.index[mask][0]
    old = g.loc[idx].copy()
    changes = []
    if (old.get("name") or "") != body.holder.strip():
        changes.append("holder name changed")
    g.loc[idx, "name"] = body.holder.strip()
    if (old.get("commodity") or "") != body.commodity:
        changes.append(f"commodity {old.get('commodity')} → {body.commodity}")
    g.loc[idx, "commodity"] = body.commodity
    if (old.get("tiptmb") or "") != body.type:
        changes.append(f"type {old.get('tiptmb')} → {body.type}")
    g.loc[idx, "tiptmb"] = body.type
    if body.no.strip():
        g.loc[idx, "skblok"] = body.no.strip()
    if (old.get("valid_until") or "") != (body.expiry or ""):
        changes.append(f"expiry {body.expiry or 'cleared'}")
    g.loc[idx, "valid_until"] = body.expiry or None
    if body.prov and (old.get("prov") or "") != body.prov:
        changes.append(f"province {old.get('prov')} → {body.prov}")
        g.loc[idx, "prov"] = body.prov
    if body.kab:
        g.loc[idx, "kab"] = body.kab
    geom = geom_from_input(body.geojson, body.polygon)
    if geom is not None:
        g.loc[idx, "geometry"] = geom
        changes.append("geometry replaced")
    save_permits(g)
    n = recrosscheck_all()
    STORE.admin_log_add(user, f"Edited permit OBJ-{objectid}", " · ".join(changes) if changes else "No field changes")
    return {"ok": True, "cases_recrosschecked": n}


@app.delete("/api/admin/permits/{objectid}")
def admin_delete_permit(objectid: int, user: str = Depends(require_admin)):
    g = permits_gdf()
    mask = g["objectid"] == objectid
    if not mask.any():
        raise HTTPException(404, "unknown permit")
    row = g[mask].iloc[0]
    save_permits(g[~mask].reset_index(drop=True))
    n = recrosscheck_all()
    STORE.admin_log_add(user, f"Deleted permit OBJ-{objectid}",
                        f"{row.get('name') or '(unnamed)'} · {n} case cross-checks re-evaluated")
    return {"ok": True, "cases_recrosschecked": n}


@app.post("/api/admin/permits/reimport")
def admin_reimport_permits(user: str = Depends(require_admin)):
    reset_permits_cache()
    g = permits_gdf()
    n = recrosscheck_all()
    STORE.admin_log_add(user, "Re-imported base registry", f"{len(g)} polygons · all case cross-checks re-run")
    return {"ok": True, "cases_recrosschecked": n, "total_permits": len(g)}


@app.get("/api/admin/log")
def admin_activity_log(q: str = "", range: str = "all", user: str = Depends(require_admin)):
    since = None
    days = {"7": 7, "30": 30, "90": 90}.get(range)
    if days:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = STORE.admin_log_list(since=since, q=q or None, limit=1000)
    return {"total": STORE.admin_log_count(), "shown": len(rows), "items": rows}


@app.get("/api/admin/status")
def admin_status(user: str = Depends(require_admin)):
    g = permits_gdf()
    db_path = os.path.join(DATA, "runtime", "minewatch.db")
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    permits_mtime = (datetime.fromtimestamp(os.path.getmtime(permits_path()), tz=timezone.utc).isoformat(timespec="seconds")
                      if os.path.exists(permits_path()) else None)
    decided = len(STORE.all_active_decisions())
    return {
        "checked_at": now_iso(),
        "cards": [
            {"label": "ACTIVE DETECTION METHOD", "value": BUNDLE["meta"].get("detection_method", "—"), "sub": "Siamese change detection"},
            {"label": "CASES", "value": len(CASES), "sub": f"{len(CASES) - decided} awaiting analyst decision"},
            {"label": "PERMITS", "value": len(g), "sub": f"admin-added {int(g['admin_added'].sum())}"},
            {"label": "DATASET BUNDLE BUILT", "value": BUNDLE["meta"].get("generated_at", "—"), "sub": "cases.json"},
            {"label": "ACTIVE LOGIN SESSIONS", "value": STORE.count_active_sessions(), "sub": f"{STORE.count_admins()} Admin account(s)"},
            {"label": "DATABASE SIZE", "value": f"{db_size / 1024 / 1024:.2f} MB", "sub": "SQLite"},
        ],
        "integrations": [
            {"name": "Sentinel-2 L2A ingest", "note": f"latest after-date in bundle: {max(c['imagery']['after_date'] for c in CASES.values())}", "state": "OK"},
            {"name": "BIG Kebijakan Satu Peta registry", "note": f"permits.geojson · last written {permits_mtime or '—'}", "state": "STATIC"},
            {"name": "Alert dispatch to DLHK / Polda", "note": "mock integration · no message leaves the system", "state": "MOCK"},
        ],
    }


# --------------------------------------------------------------------- static ----
app.mount("/assets", StaticFiles(directory=os.path.join(DATA, "assets")), name="assets")
if os.path.isdir(os.path.join(DIST, "static")):
    app.mount("/static", StaticFiles(directory=os.path.join(DIST, "static")), name="static")


PUBLIC_DIR = os.environ.get("MINEWATCH_PUBLIC", os.path.join(ROOT, "public"))
if os.path.isdir(os.path.join(PUBLIC_DIR, "media")):
    app.mount("/media", StaticFiles(directory=os.path.join(PUBLIC_DIR, "media")), name="public_media")


@app.get("/", include_in_schema=False)
def landing():
    f = os.path.join(PUBLIC_DIR, "landing.html")
    if not os.path.exists(f):
        return HTMLResponse("<p>Landing page not deployed yet.</p>", 503)
    return FileResponse(f)


@app.get("/login", include_in_schema=False)
def login_page():
    f = os.path.join(PUBLIC_DIR, "login.html")
    if not os.path.exists(f):
        return HTMLResponse("<p>Login page not deployed yet.</p>", 503)
    return FileResponse(f)


@app.get("/app", include_in_schema=False)
@app.get("/app/{path:path}", include_in_schema=False)
def spa(path: str = ""):
    # Dashboard SPA pakai hash routing (#/...), jadi path di bawah /app selain
    # index.html sendiri cuma dibutuhkan buat file statis top-level (favicon dll).
    f = os.path.join(DIST, path)
    if path and os.path.isfile(f):
        return FileResponse(f)
    index = os.path.join(DIST, "index.html")
    if not os.path.exists(index):
        return HTMLResponse("<p>Frontend not built. Run <code>cd frontend && npm run build</code>.</p>", 503)
    return FileResponse(index)
