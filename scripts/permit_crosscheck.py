"""
Modul cross-check REUSABLE: polygon kandidat gangguan (hasil deteksi, entah dari
analisis NDVI manual atau nanti dari output model AI) vs polygon izin tambang resmi
(BIG/MOMI, format `data/big_satupeta_iup/iup_part_*.geojson`).

Sebelumnya logic ini ad-hoc per-kasus (lihat `analysis/polygon_crosscheck/*.json` --
hasil jadi, bukan kode reusable). Modul ini menggantikannya dengan 1 fungsi yang bisa
dipanggil untuk kasus mana pun, termasuk nanti dari dashboard (bukan cuma analisis manual).

PRINSIP PENTING (sesuai arahan project): output cross-check ini SELALU "flagged for
review" -- persentase overlap & area di luar izin BUKAN vonis otomatis "ilegal",
cuma sinyal buat analyst manusia yang review.

Perbaikan dibanding versi ad-hoc lama:
1. `permit_name` sekarang nama perusahaan yang benar (gabungan kolom `tipopr`+`nmoprt`,
   misal "PT MITRA SUKSES GLOBALINDO"), bukan dict ter-stringify yang kepotong.
2. Luas area dihitung pakai `pyproj.Geod` (geodesic, berbasis ellipsoid bumi beneran),
   bukan asumsi proyeksi tertentu -- akurat di mana pun lokasinya di Indonesia tanpa
   perlu pilih UTM zone manual.
3. Jarak dilaporkan dalam KM (geodesic), bukan "distance_deg" yang di versi lama
   nggak informatif (derajat lintang/bujur bukan satuan jarak yang konsisten).
4. Pencarian permit "nearby" pakai spatial index (bounding box filter dulu) supaya
   efisien dipanggil berkali-kali tanpa scan semua ribuan polygon izin tiap kali.
"""
import glob
import os

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import box

GEOD = Geod(ellps="WGS84")
# Path absolut relatif ke lokasi file INI, bukan cwd pemanggil -- biar nggak
# gampang break kalau dipanggil dari direktori lain (mis. dari scripts/
# vs project root). Bug ini kebukti pas inference_pipeline.py panggil
# crosscheck() dengan cwd=scripts/ (16 Nov 2026).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IUP_GLOB = os.path.join(_PROJECT_ROOT, "data", "big_satupeta_iup", "iup_part_*.geojson")

_permit_cache: gpd.GeoDataFrame | None = None


def _geodesic_area_ha(geom) -> float:
    """Luas polygon dalam hektar, dihitung geodesic (akurat global, bukan proyeksi lokal)."""
    area_m2, _ = GEOD.geometry_area_perimeter(geom)
    return abs(area_m2) / 10_000.0


def _geodesic_distance_km(point_a, point_b) -> float:
    _, _, dist_m = GEOD.inv(point_a.x, point_a.y, point_b.x, point_b.y)
    return abs(dist_m) / 1000.0


def load_permit_database(force_reload: bool = False) -> gpd.GeoDataFrame:
    """
    Load & gabungin semua file `iup_part_*.geojson` jadi satu GeoDataFrame, di-cache
    di memory (proses load ini relatif berat -- ~ribuan polygon -- jangan diulang
    tiap panggil cross-check kalau dipanggil berkali-kali, mis. dari dashboard).
    """
    global _permit_cache
    if _permit_cache is not None and not force_reload:
        return _permit_cache

    parts = sorted(glob.glob(IUP_GLOB))
    if not parts:
        raise FileNotFoundError(f"Tidak ada file izin ditemukan di pola: {IUP_GLOB}")

    gdfs = [gpd.read_file(p) for p in parts]
    merged = pd.concat(gdfs, ignore_index=True)
    merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=gdfs[0].crs)

    # Nama perusahaan yang benar & terbaca, bukan dict ter-stringify (bug versi lama)
    merged["permit_name"] = (
        merged["tipopr"].fillna("").str.strip() + " " + merged["nmoprt"].fillna("").str.strip()
    ).str.strip()

    merged.sindex  # trigger build spatial index sekali di awal
    _permit_cache = merged
    return merged


def crosscheck(
    disturbance_gdf: gpd.GeoDataFrame,
    case_name: str,
    case_label: str = "",
    search_buffer_km: float = 3.0,
) -> dict:
    """
    Cross-check 1 kumpulan polygon gangguan (disturbance) terhadap database izin resmi.

    Args:
        disturbance_gdf: GeoDataFrame polygon gangguan (CRS EPSG:4326), biasanya hasil
            deteksi (dari analisis NDVI manual sekarang, dari output model AI nanti).
        case_name: id singkat kasus (buat key/filename), mis. "kembar_emas_sultra".
        case_label: nama deskriptif kasus buat laporan, mis. "PT Kembar Emas Sultra (PT KES)".
        search_buffer_km: radius pencarian izin "nearby" di sekitar disturbance.
            3km default -- cukup buat nangkep izin yang overlap maupun yang berbatasan,
            tanpa perlu scan SELURUH database izin nasional tiap kali.

    Returns:
        dict siap dipakai dashboard / laporan -- field `permit_overlap_detail` berisi
        SEMUA izin yang overlap atau dekat, diurutkan dari overlap terbesar.
        TIDAK ada field "is_illegal" / vonis apa pun -- ini murni data pendukung buat
        human reviewer, sesuai prinsip "flagged for review" proyek ini.
    """
    if disturbance_gdf.crs is None:
        raise ValueError("disturbance_gdf harus punya CRS (harusnya EPSG:4326)")
    disturbance_gdf = disturbance_gdf.to_crs("EPSG:4326")

    permits = load_permit_database()

    total_disturbed_ha = sum(_geodesic_area_ha(g) for g in disturbance_gdf.geometry)
    disturbance_union = disturbance_gdf.geometry.union_all()
    disturbance_centroid = disturbance_union.centroid

    # Filter awal pakai bounding box langsung dari koordinat min/max + margin buffer.
    # CATATAN PENTING: JANGAN pakai `.buffer()` di geometri union yang kompleks
    # (disturbance polygon bisa ratusan bagian terpisah) -- buffer()+dissolve di GEOS
    # untuk ratusan polygon terpisah itu MAHAL dan pernah bikin proses hang bermenit-menit
    # di kasus nyata (das_kampak: 697 bagian). Bounding box dari bounds jauh lebih murah
    # dan cukup buat prefilter kasar (presisi overlap/jarak sebenarnya tetap dicek
    # geodesic per kandidat di bawah).
    buffer_deg = search_buffer_km / 111.0  # ~111km per derajat lintang, approksimasi kasar
    minx, miny, maxx, maxy = disturbance_union.bounds
    search_box = box(minx - buffer_deg, miny - buffer_deg, maxx + buffer_deg, maxy + buffer_deg)
    candidate_idx = list(permits.sindex.query(search_box, predicate="intersects"))
    candidates = permits.iloc[candidate_idx]

    overlap_detail = []
    overlap_union = None
    for _, permit_row in candidates.iterrows():
        permit_geom = permit_row.geometry
        intersection = disturbance_union.intersection(permit_geom)
        overlap_ha = _geodesic_area_ha(intersection) if not intersection.is_empty else 0.0
        dist_km = _geodesic_distance_km(disturbance_centroid, permit_geom.centroid)

        if overlap_ha <= 0.01 and dist_km > search_buffer_km:
            continue  # bukan overlap & di luar radius pencarian -- skip, bukan "nearby"

        overlap_detail.append({
            "permit_name": permit_row["permit_name"] or "(nama tidak tercatat)",
            "commodity": permit_row.get("commdt", "-"),
            "issuer": permit_row.get("issuer", "-"),
            "status_code": permit_row.get("status", None),
            "permit_area_ha": round(_geodesic_area_ha(permit_geom), 1),
            "overlap_with_disturbance_ha": round(overlap_ha, 2),
            "pct_disturbance_inside_this_permit": round(
                overlap_ha / total_disturbed_ha * 100, 1
            ) if total_disturbed_ha > 0 else 0.0,
            "distance_km_from_disturbance_centroid": round(dist_km, 3),
        })

        if overlap_ha > 0:
            overlap_union = intersection if overlap_union is None else overlap_union.union(intersection)

    overlap_detail.sort(key=lambda d: d["overlap_with_disturbance_ha"], reverse=True)

    total_overlap_ha = _geodesic_area_ha(overlap_union) if overlap_union is not None else 0.0
    outside_all_permits_ha = max(total_disturbed_ha - total_overlap_ha, 0.0)

    return {
        "case": case_name,
        "name": case_label or case_name,
        "total_disturbed_area_ha": round(total_disturbed_ha, 1),
        "total_overlap_with_any_permit_ha": round(total_overlap_ha, 1),
        "outside_all_nearby_permits_ha": round(outside_all_permits_ha, 1),
        "pct_outside_any_permit": round(
            outside_all_permits_ha / total_disturbed_ha * 100, 1
        ) if total_disturbed_ha > 0 else 0.0,
        "n_permits_found_nearby": len(overlap_detail),
        "permit_overlap_detail": overlap_detail,
        "note": "FLAGGED FOR REVIEW -- bukan vonis otomatis. Area di luar izin bisa jadi "
                "aktivitas tanpa izin, ATAU data izin yang belum lengkap/update. Butuh "
                "verifikasi analyst manusia.",
    }


if __name__ == "__main__":
    # Regression test: reproduksi kasus "kembar_emas_sultra" yang sudah pernah dianalisis
    # manual (hasil lama ada di analysis/polygon_crosscheck/crosscheck_results.json) --
    # verifikasi modul baru ini menghasilkan angka yang MASUK AKAL dibanding hasil lama,
    # bukan cuma "jalan tanpa error".
    print("=== Regression test: kasus kembar_emas_sultra ===")
    disturbance = gpd.read_file(
        "analysis/polygon_crosscheck/kembar_emas_sultra_disturbance_polygons.geojson"
    )
    result = crosscheck(
        disturbance, case_name="kembar_emas_sultra",
        case_label="PT Kembar Emas Sultra (PT KES) - Konawe Utara",
    )
    print(f"Total disturbed area : {result['total_disturbed_area_ha']} ha")
    print(f"Overlap izin resmi   : {result['total_overlap_with_any_permit_ha']} ha")
    print(f"Di luar semua izin   : {result['outside_all_nearby_permits_ha']} ha "
          f"({result['pct_outside_any_permit']}%)")
    print(f"Jumlah izin ditemukan nearby: {result['n_permits_found_nearby']}")
    print("\nTop 3 izin overlap terbesar:")
    for p in result["permit_overlap_detail"][:3]:
        print(f"  - {p['permit_name']} | overlap={p['overlap_with_disturbance_ha']}ha "
              f"({p['pct_disturbance_inside_this_permit']}%) | komoditas={p['commodity']}")

    print("\n--- Perbandingan dengan hasil lama (ad-hoc, dari crosscheck_results.json) ---")
    print("Lama : total_disturbed=2658.0 ha, outside_all_nearby_permits=1833.5 ha")
    print(f"Baru : total_disturbed={result['total_disturbed_area_ha']} ha, "
          f"outside_all_nearby_permits={result['outside_all_nearby_permits_ha']} ha")
