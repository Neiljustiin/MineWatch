"""
Registry of the 13 ground-truth pilot cases shown in the dashboard.

Every field here is copied from the MineWatch repo, not invented:
  - names / kabupaten / province / commodity / coordinates / enforcement status / sources:
      huawei-ict-illegal-mining/docs/KONTEKS_LENGKAP.md  (BAGIAN 5)
      huawei-ict-illegal-mining/data/sentinel2_pilot/download_progress_log.md
  - data quality tier + note (manual cloud QA, final state after the 14 Nov 2026 redownload):
      huawei-ict-illegal-mining/analysis/ndvi_ndmi/HASIL_NDVI_NDMI.md

Case IDs (MW-GT-xx) follow the numbering of KONTEKS_LENGKAP.md BAGIAN 5 so every row
in the dashboard can be traced back to its source entry. #5 (PT BSJ & PT KAA) is not part
of the 13-case NDVI pilot set, which is why it is absent.
"""

CASES = [
    {
        "slug": "muara_hemat_jambi", "id": "MW-GT-01",
        "loc": "Penetai, Desa Muara Hemat", "kab": "Kab. Kerinci", "prov": "Jambi",
        "com": "Au", "lat": -2.19694, "lon": 101.76250,
        "loc_precision": "Tier 2 · village centroid (Wikipedia)",
        "gt_status": "Confirmed; Satgas PKH enforcement operation completed (Nov 2026)",
        "gt_area_ha": 119.32,
        "sources": ["mediaindonesia.com", "kompas.com", "detik.com", "cnnindonesia.com"],
        "quality": "medium_caveat",
        "quality_note": "Scattered cloud in the after image; part of the red NDVI-loss patch is likely cloud shadow, not pure clearing.",
    },
    {
        "slug": "air_liki_jambi", "id": "MW-GT-02",
        "loc": "Desa Air Liki, Tabir Barat", "kab": "Kab. Merangin", "prov": "Jambi",
        "com": "Au", "lat": -1.9516528, "lon": 101.7675103,
        "loc_precision": "Tier 2 · village centroid (OSM)",
        "gt_status": "Confirmed; mining + heavy equipment found along the river (drone + resident reports)",
        "gt_area_ha": None,
        "sources": ["jambi.tribunnews.com"],
        "quality": "light_caveat",
        "quality_note": "Small cloud in a corner + slight haze; river and mining-road pattern clearly visible.",
    },
    {
        "slug": "pangkalan_jambu", "id": "MW-GT-03",
        "loc": "Desa Baru Pangkalan Jambu", "kab": "Kab. Merangin", "prov": "Jambi",
        "com": "Au", "lat": -2.1243875, "lon": 101.8707032,
        "loc_precision": "Tier 4 · sub-district centroid (coarse)",
        "gt_status": "Confirmed; 1 of 3 initial operation points",
        "gt_area_ha": None,
        "sources": ["viva.co.id", "jambi.tribunnews.com"],
        "quality": "light_caveat",
        "quality_note": "Small cloud in a corner; river/rice-field area clearly visible.",
    },
    {
        "slug": "kristalin_eka_lestari_papua", "id": "MW-GT-04",
        "loc": "PT Kristalin Eka Lestari, Kali Musairo", "kab": "Kab. Nabire", "prov": "Papua Tengah",
        "com": "Au", "lat": -3.1389082, "lon": 135.8248429,
        "loc_precision": "Tier 2 · locality centroid Makimi (OSM)",
        "gt_status": "IUP officially revoked (BKPM decree, 22 Oct 2026); 275.9 ha illegal (170.4 ha inside WIUP, 105.5 ha outside)",
        "gt_area_ha": 275.90,
        "sources": ["kompas.com", "story.kejaksaan.go.id", "BBC Indonesia", "suara.com"],
        "quality": "medium_caveat",
        "quality_note": "Before/after frames had different extents. The original analysis resized them, creating a false coastline artefact top-left; this dashboard re-aligns both images on their GeoTIFF coordinates instead.",
        "recheck_note": "Dashboard re-check (17 Nov 2026): the 2018-09-19 before image shows roughly 25-30% scattered cumulus + shadow, and the NDVI-loss overlay largely follows cloud positions. Treat this signal as unreliable until a cleaner pair is acquired.",
    },
    {
        "slug": "kembar_emas_sultra", "id": "MW-GT-06",
        "loc": "PT Kembar Emas Sultra (PT KES)", "kab": "Kab. Konawe Utara", "prov": "Sulawesi Tenggara",
        "com": "Ni", "lat": -3.293246, "lon": 122.292514,
        "loc_precision": "Tier 0/1 · official permit polygon centroid (BIG)",
        "gt_status": "Partly sealed by Satgas PKH: 26.06 ha operating without PPKH inside forest area",
        "gt_area_ha": 26.06,
        "sources": ["muarasultra.com"],
        "quality": "reliable",
        "quality_note": "Minimal cloud; red NDVI-loss area visually matches the open-pit area in the after image.",
    },
    {
        "slug": "masempo_dalle_konut", "id": "MW-GT-07",
        "loc": "PT Masempo Dalle, Desa Morombo Pantai", "kab": "Kab. Konawe Utara", "prov": "Sulawesi Tenggara",
        "com": "Ni", "lat": -3.3472840, "lon": 122.2233351,
        "loc_precision": "Tier 2 · village geocode (Morombo)",
        "gt_status": "2 suspects (Bareskrim Polri, Dec 2025): excavation outside the valid IUP",
        "gt_area_ha": None,
        "sources": ["news.detik.com"],
        "quality": "medium_caveat",
        "quality_note": "Cloud in the corners of both images; core area still visible.",
    },
    {
        "slug": "laroenai_morowali", "id": "MW-GT-08",
        "loc": "Desa Laroenai, Bungku Pesisir", "kab": "Kab. Morowali", "prov": "Sulawesi Tengah",
        "com": "Ni", "lat": -3.0501986, "lon": 122.2776217,
        "loc_precision": "Tier 2 · village centroid",
        "gt_status": "Cleared by Satgas PKH (Nov 2025), 62.5 ha",
        "gt_area_ha": 62.5,
        "sources": ["kompas.tv", "adatah.com", "kemhan.go.id"],
        "quality": "reliable",
        "quality_note": "Mostly clean (small cloud bottom-left); coastal nickel pit clearly expanded.",
    },
    {
        "slug": "bumi_morowali_utama", "id": "MW-GT-09A",
        "loc": "PT Bumi Morowali Utama (BMU)", "kab": "Kab. Morowali", "prov": "Sulawesi Tengah",
        "com": "Ni", "lat": -3.064594, "lon": 122.248983,
        "loc_precision": "Tier 0/1 · official permit polygon centroid (BIG, 1,963 ha)",
        "gt_status": "62.15 ha opened without IPPKH/PPKH (46.03 ha inside IUP, 15.94 ha outside)",
        "gt_area_ha": 62.15,
        "sources": ["nikel.co.id", "IMA (Indonesian Mining Association)"],
        "quality": "medium_caveat",
        "quality_note": "Moderate cloud in the before image; orange pit area visible in both.",
    },
    {
        "slug": "daya_sumber_mining", "id": "MW-GT-09B",
        "loc": "PT Daya Sumber Mining Indonesia (DSMI)", "kab": "Kab. Morowali", "prov": "Sulawesi Tengah",
        "com": "Ni", "lat": -2.756180, "lon": 121.827973,
        "loc_precision": "Tier 0/1 · official permit polygon centroid (BIG, 2,199 ha)",
        "gt_status": "Identified by Satgas PKH among 16 companies (Nov 2025)",
        "gt_area_ha": None,
        "sources": ["nikel.co.id"],
        "quality": "reliable",
        "quality_note": "Both frames mostly clean; NDVI-loss cluster sits on the expanding pit.",
    },
    {
        "slug": "asmin_koalindo_tuhup", "id": "MW-GT-10",
        "loc": "PT Asmin Koalindo Tuhup (AKT)", "kab": "Kab. Murung Raya", "prov": "Kalimantan Tengah",
        "com": "C", "lat": -0.912333, "lon": 114.414167,
        "loc_precision": "Tier 3 · cluster of neighbouring concessions (approximate)",
        "gt_status": "Seized by the state (22 Jan 2026); IUP revoked since 2017; fine Rp4.2 T",
        "gt_area_ha": 1699.0,
        "sources": ["bpkp.go.id"],
        "quality": "medium_caveat",
        "quality_note": "Residual scattered cloud (~15-20%) in both frames; the red cluster on the right correlates with cloud position.",
    },
    {
        "slug": "singlurus_pratama", "id": "MW-GT-11",
        "loc": "PT Singlurus Pratama, Tahura Bukit Soeharto", "kab": "Kab. Kutai Kartanegara", "prov": "Kalimantan Timur",
        "com": "C", "lat": -1.030749, "lon": 117.002146,
        "loc_precision": "Tier 0/1 · official permit polygon centroid (BIG, 21,699 ha)",
        "gt_status": "Seized by the state (31 Aug 2026); 111.71 ha inside protected forest park",
        "gt_area_ha": 111.71,
        "sources": ["kalsel.antaranews.com"],
        "quality": "reliable",
        "quality_note": "Minor diagonal cloud band in the before image, not over the mine; expansion clearly visible.",
    },
    {
        "slug": "das_kampak_bangkabarat", "id": "MW-GT-12",
        "loc": "DAS Kampak, Jebus", "kab": "Kab. Bangka Barat", "prov": "Kep. Bangka Belitung",
        "com": "Sn", "lat": -1.7711586, "lon": 105.4650541,
        "loc_precision": "Tier 2 · village centroid (Jebus)",
        "gt_status": "Repeatedly cleared (Aug-Nov 2026), suspected to resume operating",
        "gt_area_ha": None,
        "sources": ["babel.antaranews.com", "wowbabel.com", "bangka.tribunnews.com"],
        "quality": "reliable",
        "quality_note": "Clean imagery; river and tin-mining ponds clearly visible.",
    },
    {
        "slug": "dusun_nadi_bangkatengah", "id": "MW-GT-13",
        "loc": "Dusun Nadi, Lubuk Besar", "kab": "Kab. Bangka Tengah", "prov": "Kep. Bangka Belitung",
        "com": "Sn", "lat": -2.6298323, "lon": 106.5962804,
        "loc_precision": "Tier 2 · village centroid (Lubuk Besar)",
        "gt_status": "Inspected by the Attorney General (19 Nov 2025); dozens of excavators seized",
        "gt_area_ha": None,
        "sources": ["bangka.tribunnews.com"],
        "quality": "reliable",
        "quality_note": "Cloud much reduced after redownload; coastal pit clearly visible in both frames.",
    },
]

QUALITY_LABELS = {
    "reliable": "Reliable",
    "light_caveat": "Light caveat",
    "medium_caveat": "Medium caveat",
    "unreliable": "Unreliable",
}
