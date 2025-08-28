from __future__ import annotations
import base64
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageOps
from sqlalchemy import text
from werkzeug.utils import secure_filename

from config import Config
from db import ENGINE

# ---------- Util kecil ----------
def _split_schema_object(qualified: str):
    parts = qualified.strip().strip("[]").split(".", 1)
    if len(parts) == 1:
        return "dbo", parts[0]
    return parts[0], parts[1]

def _quoted(schema: str, name: str) -> str:
    return f"[{schema}].[{name}]"

def _get_columns(conn, schema: str, name: str):
    rows = conn.execute(
        text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :s AND TABLE_NAME = :n
            ORDER BY ORDINAL_POSITION
        """),
        {"s": schema, "n": name}
    ).all()
    return [r[0] for r in rows]

def _img_has_col(conn, col: str) -> bool:
    cols = _get_columns(conn, Config.IMG_SCHEMA, Config.IMG_TABLE)
    return any(c.lower() == col.lower() for c in cols)

def _map_view_columns(conn):
    vschema, vname = _split_schema_object(Config.LIST_VIEW)
    all_cols = _get_columns(conn, vschema, vname)
    lower = {c.lower(): c for c in all_cols}

    id_candidates = ["Equipment","EquipmentID","EquipmentId","Equipment_ID",
                     "EquipmentKey","EquipmentCode","Code","Id","ID"]
    name_candidates = ["EquipmentName","Name","EquipmentDesc","Description","Nama","Title"]
    upd_candidates  = ["UpdatedAt","UpdatedDate","UpdateDate","ModifiedAt","ModifiedDate",
                       "LastUpdate","LastUpdated","LastModified","TanggalUpdate"]
    by_candidates   = ["CreatedBy","CreateBy","UpdatedBy","User","Username","Created_User","CreatedByName","UpdateBY"]

    pick = lambda cand: next((lower.get(c.lower()) for c in cand if c.lower() in lower), None)

    id_col = pick(id_candidates)
    name_col = next((lower.get(c.lower()) for c in name_candidates
                     if c.lower() in lower and lower.get(c.lower()) != id_col), None)
    return {
        "all_cols": all_cols,
        "id_col": id_col,
        "name_col": name_col,
        "updated_col": pick(upd_candidates),
        "createdby_col": pick(by_candidates),
        "schema": vschema, "name": vname,
    }

def _pick_variant(row_lower: dict, keys, avoid: str | None = None):
    for k in keys:
        if not k: continue
        lk = k.lower()
        if lk in row_lower:
            if not avoid or lk != avoid.lower():
                val = row_lower[lk]
                if val is not None and str(val).strip() != "":
                    return val
    return None

def as_browser_src(val):
    if not val:
        return None
    s = str(val)
    if s.startswith(("data:", "http://", "https://")):
        return s
    if s.startswith("iVBORw0KGgo"):   mime = "image/png"
    elif s.startswith("/9j/"):         mime = "image/jpeg"
    elif s.startswith("R0lGOD"):       mime = "image/gif"
    elif s.startswith("UklGR"):        mime = "image/webp"
    else:                              mime = "application/octet-stream"
    return f"data:{mime};base64,{s}"

# ---------- LIST ----------
def fetch_created_equipment_list(q: str = "", page: int = 1, per_page: int = 25):
    with ENGINE.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT Equipment AS id,
                   COALESCE([{Config.IMG_NAMECOL}], Equipment) AS name,
                   Depan, Belakang, Kanan, Kiri,
                   LastUpdate, UpdateBY
            FROM [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}]
            ORDER BY LastUpdate DESC, Equipment DESC
        """)).mappings().all()

    items = []
    q_norm = (q or "").strip().lower()
    for r in rows:
        name = str(r["name"] or r["id"])
        if q_norm and (q_norm not in name.lower() and q_norm not in str(r["id"]).lower()):
            continue
        items.append(SimpleNamespace(
            id=str(r["id"]),
            name=name,
            created_by=r.get("UpdateBY"),
            updated_at=r.get("LastUpdate") or datetime.utcnow(),
            front_image=as_browser_src(r.get("Depan")),
            rear_image=as_browser_src(r.get("Belakang")),
            right_image=as_browser_src(r.get("Kanan")),
            left_image=as_browser_src(r.get("Kiri")),
            image_count=lambda e=None, rr=r: sum(1 for x in [rr.get("Depan"), rr.get("Belakang"), rr.get("Kanan"), rr.get("Kiri")] if x),
        ))

    total_all = len(items)
    start = max(0, (page - 1) * per_page)
    end = start + per_page
    return items[start:end], total_all

def get_existing_names_set():
    with ENGINE.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT UPPER(COALESCE([{Config.IMG_NAMECOL}], Equipment)) AS nm
            FROM [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}]
        """)).all()
    return {str(r[0]).upper() for r in rows}

def create_empty_equipment_row(equipment_name: str, created_by: str = "admin"):
    with ENGINE.begin() as conn:
        if _img_has_col(conn, Config.IMG_NAMECOL):
            conn.execute(text(f"""
                IF NOT EXISTS (SELECT 1 FROM [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}] WHERE Equipment = :eid)
                BEGIN
                  INSERT INTO [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}]
                    (Equipment, [{Config.IMG_NAMECOL}], LastUpdate, UpdateBY)
                  VALUES (:eid, :nm, SYSDATETIME(), :ub)
                END
            """), {"eid": equipment_name, "nm": equipment_name, "ub": created_by})
        else:
            conn.execute(text(f"""
                IF NOT EXISTS (SELECT 1 FROM [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}] WHERE Equipment = :eid)
                BEGIN
                  INSERT INTO [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}]
                    (Equipment, LastUpdate, UpdateBY)
                  VALUES (:eid, SYSDATETIME(), :ub)
                END
            """), {"eid": equipment_name, "ub": created_by})

# ---------- DETAIL ----------
def fetch_equipment_one(equipment_id: str):
    with ENGINE.connect() as conn:
        v = _map_view_columns(conn)
        view_qq = _quoted(v["schema"], v["name"])
        has_listname = _img_has_col(conn, Config.IMG_NAMECOL)
        sel_listname = f", i.[{Config.IMG_NAMECOL}] AS __list_name" if has_listname else ""
        if not v["id_col"]:
            return None
        row = conn.execute(text(f"""
            SELECT v.*,
                   i.Depan     AS __img_front,
                   i.Belakang  AS __img_rear,
                   i.Kanan     AS __img_right,
                   i.Kiri      AS __img_left,
                   i.LastUpdate AS __img_lastupdate,
                   i.UpdateBY   AS __img_updateby
                   {sel_listname}
            FROM {view_qq} AS v
            LEFT JOIN [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}] AS i
              ON CAST(i.Equipment AS NVARCHAR(255)) = CAST(v.[{v['id_col']}] AS NVARCHAR(255))
            WHERE v.[{v['id_col']}] = :x
        """), {"x": equipment_id}).mappings().first()
        if not row: return None
        r_l = {k.lower(): row[k] for k in row.keys()}
        name = (r_l.get("__list_name") or
                _pick_variant(r_l, [v["name_col"], "equipmentname","name","equipmentdesc","description","nama","title"],
                              avoid=v["id_col"]) or str(equipment_id))
        updated = (r_l.get("__img_lastupdate") or
                   _pick_variant(r_l, [v["updated_col"], "lastupdate","updateddate","updatedat"])) or datetime.utcnow()
        created_by = (r_l.get("__img_updateby") or
                      _pick_variant(r_l, [v["createdby_col"], "updateby","createdby","username","user"]))
        return SimpleNamespace(
            id=str(equipment_id),
            name=str(name),
            created_by=created_by,
            updated_at=updated,
            front_image=as_browser_src(r_l.get("__img_front")),
            rear_image=as_browser_src(r_l.get("__img_rear")),
            right_image=as_browser_src(r_l.get("__img_right")),
            left_image=as_browser_src(r_l.get("__img_left")),
            image_count=lambda e=None: sum(1 for x in [
                as_browser_src(r_l.get("__img_front")),
                as_browser_src(r_l.get("__img_rear")),
                as_browser_src(r_l.get("__img_right")),
                as_browser_src(r_l.get("__img_left"))
            ] if x),
        )

# ---------- Upload helpers ----------
def allowed(filename: str, mimetype: str | None = None) -> bool:
    if mimetype and str(mimetype).lower().startswith("image/"):
        return True
    if "." in (filename or ""):
        ext = filename.rsplit(".", 1)[1].lower()
        if ext in Config.ALLOWED_EXTENSIONS:
            return True
    return True

def _ext_from_mime(mime: str) -> str:
    mime = (mime or "").lower()
    if mime.endswith("jpeg"): return "jpg"
    if mime.endswith("png"):  return "png"
    if mime.endswith("webp"): return "webp"
    if mime.endswith("gif"):  return "gif"
    return "jpg"

POSITION_NAME = {
    "front": "front_view",
    "rear":  "rear_view",
    "right": "right_side_view",
    "left":  "left_side_view",
}
def _build_canonical_filename(equipment_id: str, view: str, mime: str) -> str:
    ext = _ext_from_mime(mime)
    base = f"{equipment_id}_{POSITION_NAME[view]}"
    return secure_filename(f"{base}.{ext}")

def _standardize_to_data_uri(file_storage, *, filename: str | None = None) -> str:
    cfg = Config
    fmt = str(cfg.STD_IMAGE_FORMAT).upper()              # JPEG/WEBP/PNG
    tgt_w = int(cfg.STD_IMAGE_WIDTH)
    tgt_h = int(cfg.STD_IMAGE_HEIGHT)
    mode  = str(cfg.STD_IMAGE_MODE).upper()              # FIT/PAD/CROP
    q_init = int(cfg.STD_IMAGE_QUALITY)
    max_bytes = int(cfg.STD_IMAGE_MAX_BYTES)

    img = Image.open(file_storage.stream)
    img = ImageOps.exif_transpose(img)

    if fmt in ("JPEG", "WEBP"):
        img = img.convert("RGB")

    if mode == "FIT":
        img.thumbnail((tgt_w, tgt_h), Image.Resampling.LANCZOS)
        canvas = img
    elif mode == "PAD":
        ratio = min(tgt_w / img.width, tgt_h / img.height)
        new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        from PIL import Image as PILImage
        bg = PILImage.new("RGB" if fmt in ("JPEG","WEBP") else "RGBA",
                          (tgt_w, tgt_h),
                          (255,255,255) if fmt in ("JPEG","WEBP") else (255,255,255,0))
        bg.paste(img, ((tgt_w - new_size[0]) // 2, (tgt_h - new_size[1]) // 2))
        canvas = bg
    elif mode == "CROP":
        ratio = max(tgt_w / img.width, tgt_h / img.height)
        new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        left = (img.width - tgt_w) // 2
        top  = (img.height - tgt_h) // 2
        canvas = img.crop((left, top, left + tgt_w, top + tgt_h))
    else:
        canvas = img

    mime = {"JPEG": "image/jpeg", "WEBP": "image/webp", "PNG": "image/png"}.get(fmt, "image/jpeg")
    save_params = {}
    if fmt == "JPEG":
        save_params = dict(format="JPEG", optimize=True, progressive=True)
    elif fmt == "WEBP":
        save_params = dict(format="WEBP", method=6)
    else:
        save_params = dict(format="PNG", optimize=True)

    buf = BytesIO()
    q = q_init
    while True:
        buf.seek(0); buf.truncate(0)
        if fmt in ("JPEG", "WEBP"):
            canvas.save(buf, quality=q, **save_params)
        else:
            canvas.save(buf, **save_params)
        size = buf.tell()
        if size <= max_bytes or fmt == "PNG" or q <= 60:
            break
        q -= 5

    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    name_part = f";name={secure_filename(filename)}" if filename else ""
    return f"data:{mime}{name_part};base64,{b64}"

def to_data_uri_with_std_name(file_storage, equipment_id: str, view: str) -> str:
    fmt = str(Config.STD_IMAGE_FORMAT).upper()
    mime = {"JPEG": "image/jpeg", "WEBP": "image/webp", "PNG": "image/png"}.get(fmt, "image/jpeg")
    filename = _build_canonical_filename(equipment_id, view, mime)
    return _standardize_to_data_uri(file_storage, filename=filename)

def _ensure_named_data_uri(data_uri: str, equipment_id: str, view: str) -> str:
    if not data_uri or ";name=" in data_uri or not data_uri.startswith("data:image"):
        return data_uri
    head = data_uri.split(";", 1)[0]
    mime = head[5:]
    filename = _build_canonical_filename(equipment_id, view, mime)
    return data_uri.replace(";base64,", f";name={secure_filename(filename)};base64,", 1)

VIEW_COL = {"front": "Depan", "rear": "Belakang", "right": "Kanan", "left": "Kiri"}

def upsert_image_meta(equipment_id: str, view: str, data_uri: str, updated_by: str | None):
    data_uri = _ensure_named_data_uri(data_uri, equipment_id, view)
    col = VIEW_COL[view]
    with ENGINE.begin() as conn:
        result = conn.execute(
            text(f"""
                UPDATE [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}]
                SET [{col}] = :val, LastUpdate = SYSDATETIME(), UpdateBY = :ub
                WHERE Equipment = :eid
            """),
            {"val": data_uri, "eid": equipment_id, "ub": updated_by}
        )
        if result.rowcount == 0:
            conn.execute(
                text(f"""
                    INSERT INTO [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}] (Equipment, [{col}], LastUpdate, UpdateBY)
                    VALUES (:eid, :val, SYSDATETIME(), :ub)
                """),
                {"eid": equipment_id, "val": data_uri, "ub": updated_by}
            )

def remove_image_meta(equipment_id: str, view: str):
    col = VIEW_COL[view]
    with ENGINE.begin() as conn:
        conn.execute(
            text(f"""
                UPDATE [{Config.IMG_SCHEMA}].[{Config.IMG_TABLE}]
                SET [{col}] = NULL, LastUpdate = SYSDATETIME()
                WHERE Equipment = :eid
            """),
            {"eid": equipment_id}
        )
