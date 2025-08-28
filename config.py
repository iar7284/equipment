import os
from pathlib import Path

class Config:
    # ----- App -----
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    BASE_DIR = Path(__file__).resolve().parent
    PER_PAGE = int(os.getenv("PER_PAGE", "25"))

    # ----- Upload roots -----
    # Folder penyimpanan lokal aplikasi (dipakai kalau kamu simpan file fisik)
    UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", str(BASE_DIR / "static" / "uploads"))
    # Folder "repo" eksternal (misal koleksi gambar existing di luar app)
    FOLDER_REPO_ROOT = os.getenv(
        "FOLDER_REPO_ROOT",
        r"D:\IMAGES"
    )
    # Back-compat untuk kode lama yang masih refer ke REPO_ROOT
    REPO_ROOT = FOLDER_REPO_ROOT

    # Validasi file & batas ukuran unggahan
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "jfif"}
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "200")) * 1024 * 1024

    # Standarisasi gambar (dipakai di services.equipment_service.to_data_uri_with_std_name)
    # FORMAT: JPEG | WEBP | PNG
    STD_IMAGE_FORMAT = os.getenv("STD_IMAGE_FORMAT", "JPEG")
    STD_IMAGE_WIDTH  = int(os.getenv("STD_IMAGE_WIDTH", "1024"))
    STD_IMAGE_HEIGHT = int(os.getenv("STD_IMAGE_HEIGHT", "768"))
    # MODE: FIT (maintain ratio), PAD (kanvas), CROP (isi penuh lalu crop)
    STD_IMAGE_MODE   = os.getenv("STD_IMAGE_MODE", "FIT")
    STD_IMAGE_QUALITY = int(os.getenv("STD_IMAGE_QUALITY", "85"))
    # Batas bytes hasil kompres final; default ikut MAX_CONTENT_LENGTH jika ada, fallback 1MB
    STD_IMAGE_MAX_BYTES = int(os.getenv("STD_IMAGE_MAX_BYTES", str(1 * 1024 * 1024)))

    # ----- Views/Labels untuk gambar -----
    EXPECTED_VIEWS = {"front", "rear", "left", "right"}
    VIEW_LABELS = {
        "front": "Front",
        "rear": "Rear",
        "left": "Left",
        "right": "Right",
    }

    # ----- Sumber nama/ID equipment (untuk suggest/autocomplete fallback) -----
    EQUIPMENT_NAMES_FILE = os.getenv(
        "EQUIPMENT_NAMES_FILE",
        str(BASE_DIR / "data" / "equipment_names.txt")
    )

    # ----- Database (SQL Server) -----
    DB_SERVER   = os.getenv("DB_SERVER", "sqlmisis-prod.public.6273d55d722a.database.windows.net,3342")
    DB_NAME     = os.getenv("DB_NAME", "dwstage")
    DB_USER     = os.getenv("DB_USER", "dwread")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "dwsis123!")

    # View untuk list; minimal punya kolom ID & (opsional) Name
    LIST_VIEW   = os.getenv("LIST_VIEW", "dbo.v_ListEquipment")
    # Nama kolom yang jadi "nama tampilan" untuk badge/list (dipakai juga saat join)
    IMG_NAMECOL = os.getenv("IMG_NAMECOL", "Equipment")

    # Tabel metadata gambar
    IMG_SCHEMA  = os.getenv("IMG_SCHEMA", "Stage")
    IMG_TABLE   = os.getenv("IMG_TABLE", "EquipmentImages")
    
    # Dev cookies
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_PERMANENT = False
