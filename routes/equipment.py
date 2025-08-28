from math import ceil
import os, mimetypes, glob
from flask import (
    Blueprint, render_template, redirect, url_for,
    request, flash, jsonify, send_file, abort
)

from config import Config
from services.equipment_service import (
    # list + add
    fetch_created_equipment_list,
    create_empty_equipment_row,
    get_existing_names_set,
    # detail + image ops
    fetch_equipment_one,
    allowed,
    to_data_uri_with_std_name,
    upsert_image_meta,
    remove_image_meta,
)
from services import equipment_names

equipment_bp = Blueprint("equipment", __name__, url_prefix="/equipment")

# ---------------- Pagination helper ----------------
def _page_window(cur: int, total: int, width: int = 5):
    if total <= width:
        return list(range(1, total + 1))
    half = width // 2
    start = max(1, cur - half)
    end = min(total, start + width - 1)
    start = max(1, end - width + 1)
    pages = []
    if start > 1:
        pages += [1, None]
    pages += list(range(start, end + 1))
    if end < total:
        pages += [None, total]
    return pages

# ---------------- Thumbnail helper ----------------
ALLOWED_EXTS = tuple("." + e for e in Config.ALLOWED_EXTENSIONS)

def _first_image_path(equipment_name: str) -> str | None:
    """
    Cari file gambar pertama untuk equipment:
    - pola: <base>/<name>/*.{ext}  atau  <base>/<name>/<view>.{ext}
    - base: UPLOAD_ROOT, REPO_ROOT (alias ke FOLDER_REPO_ROOT)
    - ext: ALLOWED_EXTENSIONS
    """
    name = (equipment_name or "").strip()
    if not name:
        return None

    bases = [Config.UPLOAD_ROOT, getattr(Config, "REPO_ROOT", None)]
    views = list(getattr(Config, "EXPECTED_VIEWS", []))
    for base in bases:
        if not base:
            continue
        base_dir = os.path.join(base, name)
        if not os.path.isdir(base_dir):
            continue

        # 1) coba <view>.<ext> lebih dulu
        for v in views:
            for ext in Config.ALLOWED_EXTENSIONS:
                p = os.path.join(base_dir, f"{v}.{ext}")
                if os.path.isfile(p):
                    return p

        # 2) fallback: file gambar pertama
        for path in sorted(glob.glob(os.path.join(base_dir, "*"))):
            if os.path.isfile(path) and path.lower().endswith(ALLOWED_EXTS):
                return path
    return None

@equipment_bp.get("/thumb/<path:name>")
def thumb(name: str):
    """
    Layani file thumbnail sebagai response binary.
    name = nama equipment (folder).
    """
    p = _first_image_path(name)
    if not p or not os.path.isfile(p):
        abort(404)
    mime, _ = mimetypes.guess_type(p)
    return send_file(p, mimetype=mime or "application/octet-stream")

# ---------------- List ----------------
@equipment_bp.route("/", endpoint="list")
@equipment_bp.route("")
def list_():
    q = (request.args.get("q") or "").strip()
    page = max(int(request.args.get("page", "1") or 1), 1)
    per_page = Config.PER_PAGE

    items, total = fetch_created_equipment_list(q=q, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    pages = _page_window(page, total_pages)

    # Bangun mapping thumbnails: jika ketemu file → pakai endpoint /thumb/...
    thumbs = {}
    for it in items:
        if _first_image_path(it.name):
            thumbs[it.id] = url_for("equipment.thumb", name=str(it.name))

    return render_template(
        "equipment_list.html",
        title="Equipment List",
        items=items,
        thumbs=thumbs,
        q=q,
        page=page,
        pages=pages,
        total_pages=total_pages,
    )

# ---------------- Add New (page) ----------------
@equipment_bp.get("/new", endpoint="new")
def new():
    # tampilkan halaman form Add New
    return render_template("equipment_new.html", title="Add New Equipment")

@equipment_bp.get("/options")
def options():
    term = (request.args.get("q") or "").strip().upper()
    limit = max(1, min(int(request.args.get("limit", "10") or 10), 50))
    if len(term) < 3:
        return jsonify([])

    _, mapping = equipment_names.get_all_unit_names()
    existing = get_existing_names_set()

    results = []
    for key, canonical in mapping.items():
        if canonical.upper() in existing:
            continue
        if term in key or term in canonical.upper():
            results.append({"id": canonical, "name": canonical})
            if len(results) >= limit:
                break
    return jsonify(results)

@equipment_bp.post("/create")
def create():
    selected = (request.form.get("equipment_id") or "").strip()
    q = (request.form.get("q") or "").strip()

    if not selected and len(q) < 3:
        flash("Silakan pilih dari sugesti atau ketik minimal 3 huruf.", "warning")
        return redirect(url_for("equipment.list", open="new"))

    _, mapping = equipment_names.get_all_unit_names()
    existing = get_existing_names_set()

    if selected:
        canonical = mapping.get(selected.upper(), selected)
    else:
        key = q.upper()
        if key in mapping:
            canonical = mapping[key]
        else:
            hits = [v for k, v in mapping.items() if key in k]
            if not hits:
                flash("Nama/ID tidak ditemukan.", "warning")
                return redirect(url_for("equipment.list", open="new"))
            if len(hits) > 1:
                flash("Terlalu banyak hasil. Perjelas pencarian.", "warning")
                return redirect(url_for("equipment.list", open="new"))
            canonical = hits[0]

    if canonical.upper() in existing:
        flash(f"Equipment '{canonical}' sudah ada di list.", "info")
        return redirect(url_for("equipment.list", q=canonical))

    create_empty_equipment_row(canonical, created_by="admin")
    flash(f"Equipment '{canonical}' ditambahkan.", "success")
    return redirect(url_for("equipment.list", q=canonical))

# ---------------- Detail + Upload/Remove ----------------
@equipment_bp.get("/<string:equipment_id>", endpoint="detail")
def detail(equipment_id: str):
    """Halaman detail 4-view (front/rear/right/left)."""
    item = fetch_equipment_one(equipment_id)
    if not item:
        flash("Equipment tidak ditemukan.", "danger")
        return redirect(url_for("equipment.list"))

    VIEWS = ["front", "rear", "right", "left"]
    view_labels = {
        "front": "Front View",
        "rear": "Rear View",
        "right": "Right Side View",
        "left": "Left Side View",
    }
    images = {
        "front": item.front_image,
        "rear": item.rear_image,
        "right": item.right_image,
        "left": item.left_image,
    }

    return render_template(
        "equipment_detail.html",
        eq=item,
        VIEWS=VIEWS,
        view_labels=view_labels,
        images=images,
        title=item.name,
    )

@equipment_bp.post("/<string:equipment_id>/upload/<string:view>", endpoint="upload_view")
def upload_view(equipment_id: str, view: str):
    """Upload satu view gambar."""
    v = (view or "").lower()
    if v not in {"front", "rear", "right", "left"}:
        flash("Posisi gambar tidak valid.", "danger")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id))

    file = request.files.get("image")
    if not file or file.filename == "":
        flash("Tidak ada file yang dipilih.", "warning")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id))

    if not allowed(file.filename, getattr(file, "mimetype", None)):
        flash("File tidak didukung.", "danger")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id))

    try:
        data_uri = to_data_uri_with_std_name(file, equipment_id=equipment_id, view=v)
        upsert_image_meta(equipment_id, v, data_uri, updated_by="admin")
        flash("Gambar berhasil diunggah.", "success")
    except Exception as e:
        flash(f"Gagal menyimpan metadata ke DB: {e}", "danger")

    return redirect(url_for("equipment.detail", equipment_id=equipment_id))

@equipment_bp.post("/<string:equipment_id>/remove/<string:view>", endpoint="remove_view")
def remove_view(equipment_id: str, view: str):
    """Hapus satu view gambar."""
    v = (view or "").lower()
    if v not in {"front", "rear", "right", "left"}:
        flash("Posisi gambar tidak valid.", "danger")
        return redirect(url_for("equipment.detail", equipment_id=equipment_id))

    try:
        remove_image_meta(equipment_id, v)
        flash("Gambar dihapus.", "success")
    except Exception as e:
        flash(f"Gagal menghapus metadata di DB: {e}", "danger")

    return redirect(url_for("equipment.detail", equipment_id=equipment_id))
