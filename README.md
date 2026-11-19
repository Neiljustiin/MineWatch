# MineWatch

Illegal-mining detection for Indonesia, built by team **kulonuwun** (Telkom
University) for the **11th Huawei ICT Competition — Innovation Track**.

MineWatch flags possible illegal mining activity by combining satellite
change detection with Indonesia's own official mining-permit registry, so an
analyst can cross-check a suspected site against real permit data in seconds
instead of days. **Every result is "flagged for review" — the system never
issues an automatic legal verdict.** A flag only means "a human analyst
should look at this," not "this is confirmed illegal."

## How it works

1. **Change detection** — a Siamese change-detection network (FC-Siam-diff,
   Daudt et al. 2018) compares a "before" and "after" Sentinel-2 image of the
   same location and predicts where bare ground newly appeared (a proxy for
   land clearing / open-pit expansion).
2. **Permit cross-check** — every flagged location is checked against BIG's
   official KSP SatuPeta permit layer (IUP/IUPK/IPR/KK/PKP2B polygons) to see
   whether it falls inside, outside, or on an expired permit.
3. **Review, not verdict** — the combined result (detection + permit status)
   is surfaced to a human analyst on a dashboard for sign-off. Nothing is
   auto-reported to any authority.

## Repository layout

This repo is split across branches instead of folders — each branch is a
runnable project on its own:

| Branch | Contents |
|---|---|
| [`training`](../../tree/training) | Dataset curation, FC-Siam-diff model code, training/eval scripts, competition submission documents (pitch deck, entry form) |
| [`dashboard`](../../tree/dashboard) | The analyst-facing web app — FastAPI backend + React/Vite/Leaflet frontend, permit cross-check pipeline, admin/RBAC panel |
| `main` (this branch) | Project overview only |

Large training data and model checkpoints are intentionally not committed
(see each branch's `.gitignore`) — only code, scripts, and documents are
version-controlled here.

## Current status

- Model trained through iteration v5 on the MineNetCD256 benchmark dataset
  plus Indonesia-specific samples (Jasansky et al. mining dataset, STAC-sourced
  Sentinel-2 pairs); evaluated on a held-out Indonesian test split.
- Dashboard currently ships 13 manually-verified ground-truth pilot cases as
  a validated baseline. The next milestone is running the trained model
  directly over a wider area of Indonesia to produce its own candidate
  detections — shown separately from the verified ground-truth set so the
  two are never confused.
- Target cloud footprint: **Huawei Cloud ECS** (dashboard/API hosting) +
  **OBS** (dataset/model/permit storage), region AP-Jakarta. Model training
  currently runs on the team's own GPU hardware, not a managed Huawei AI
  service.

## Team — kulonuwun (Telkom University)

- Prajna Deshanta Ibnugraha — supervising instructor
- Muhammad Rafi Gunawan — team leader
- Siti Nurhayati Syafaningrum
- Neil Justin Surupati

## References

See `training/docs/REFERENCES.md` for the papers and public datasets this
project builds on (MineNetCD benchmark, FC-Siam-diff, Focal/Tversky loss,
earthrise-media's Amazon Mining Watch as a real-world precedent).
