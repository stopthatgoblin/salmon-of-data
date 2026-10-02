"""Prespecified simple-model diagnostics with no shared dates across folds.

These fits are against provisional, threshold-filtered probe values and generic
Sen2Cor BOA. They are NOT local turbidity validation or production models.
"""
import collections
import csv
import datetime as dt
import hashlib
import json
import math

import numpy as np

from build_matchups import OUTPUT, write_csv

MODELS = ["training_median", "station_median", "seasonal_harmonic", "red_linear",
          "nir_linear", "red_nir_linear", "red_green_ratio", "nir_red_ratio"]


def number(row, name):
    return float(row[name])


def features(row, model):
    if model == "seasonal_harmonic":
        day = dt.date.fromisoformat(row["overpass_group"]).timetuple().tm_yday
        return [math.sin(2*math.pi*day/365.2425), math.cos(2*math.pi*day/365.2425)]
    if model == "red_linear":
        return [number(row, "red_median")]
    if model == "nir_linear":
        return [number(row, "nir_median")]
    if model == "red_nir_linear":
        return [number(row, "red_median"), number(row, "nir_median")]
    if model == "red_green_ratio":
        return [number(row, "red_median")/number(row, "green_median")]
    if model == "nir_red_ratio":
        return [number(row, "nir_median")/number(row, "red_median")]
    return []


def predict(train, test, model):
    y = np.array([number(r, "probe_value") for r in train])
    if model in ["training_median", "station_median"]:
        result = []
        for r in test:
            local = [number(t, "probe_value") for t in train if t["station"] == r["station"]]
            result.append(float(np.median(local if model == "station_median" and local else y)))
        return np.array(result), np.zeros(len(test), dtype=bool)
    x = np.array([features(r, model) for r in train])
    z = np.array([features(r, model) for r in test])
    # Only training statistics enter transformations/fitting.
    centre, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 0, scale, 1)
    xx = np.column_stack([np.ones(len(x)), (x-centre)/scale])
    zz = np.column_stack([np.ones(len(z)), (z-centre)/scale])
    coefficients = np.linalg.lstsq(xx, y, rcond=None)[0]
    outside = ((z < x.min(axis=0)) | (z > x.max(axis=0))).any(axis=1)
    return zz @ coefficients, outside


def splits(rows, scheme):
    dates = sorted({r["overpass_group"] for r in rows})
    if scheme == "leave_one_date_out":
        for date in dates:
            yield date, [r for r in rows if r["overpass_group"] != date], [r for r in rows if r["overpass_group"] == date]
    elif scheme == "forward_blocks":
        for start, end in [(.4, .6), (.6, .8), (.8, 1.)]:
            train_dates = set(dates[:int(len(dates)*start)])
            test_dates = set(dates[int(len(dates)*start):int(len(dates)*end)])
            yield f"forward_{start}_{end}", [r for r in rows if r["overpass_group"] in train_dates], [r for r in rows if r["overpass_group"] in test_dates]
    elif scheme == "station_and_date_holdout":
        for station in sorted({r["station"] for r in rows}):
            test = [r for r in rows if r["station"] == station]
            test_dates = {r["overpass_group"] for r in test}
            train = [r for r in rows if r["station"] != station and r["overpass_group"] not in test_dates]
            yield station, train, test
    else:
        raise ValueError(scheme)


def metrics(observed, predicted):
    y, p = np.array(observed, dtype=float), np.array(predicted, dtype=float)
    errors = p-y
    variance = ((y-y.mean())**2).sum()
    return {"n": len(y), "mae": float(np.mean(np.abs(errors))),
            "rmse": float(np.sqrt(np.mean(errors**2))), "bias": float(errors.mean()),
            "r2": float(1-(errors**2).sum()/variance) if variance > 0 else None,
            # Normalisation by the held-out mean is explicitly NOT per-row MAPE.
            "mae_percent_of_mean_observed": float(100*np.mean(np.abs(errors))/y.mean()) if y.mean() > 0 else None,
            "negative_predictions": int((p < 0).sum())}


def cluster_bootstrap(rows, repetitions=500):
    grouped = collections.defaultdict(list)
    for r in rows:
        grouped[r["date"]].append(r)
    dates = sorted(grouped)
    if len(dates) < 2:
        return None
    rng = np.random.default_rng(9232026)
    results = []
    for _ in range(repetitions):
        sample = [r for d in rng.choice(dates, len(dates), replace=True) for r in grouped[d]]
        errors = np.array([r["prediction"]-r["observed"] for r in sample])
        results.append([np.abs(errors).mean(), np.sqrt((errors**2).mean())])
    intervals = np.quantile(results, [.025, .975], axis=0)
    return {"mae_95pct_interval": intervals[:, 0].tolist(), "rmse_95pct_interval": intervals[:, 1].tolist(),
            "interpretation": "Date-cluster bootstrap sampling uncertainty in fixed out-of-fold conditional errors; excludes fitting/selection uncertainty and sensor/atmospheric systematic uncertainty; not prediction intervals."}


def evaluate(rows, schemes):
    predictions, fold_audit = [], []
    for scheme in schemes:
        for fold, train, test in splits(rows, scheme):
            train_dates = {r["overpass_group"] for r in train}
            test_dates = {r["overpass_group"] for r in test}
            if train_dates & test_dates:
                raise ValueError("Leakage: date in both training and test")
            runnable = len(train_dates) >= 8 and bool(test)
            fold_audit.append({"scheme": scheme, "fold": fold, "train_dates": len(train_dates),
                               "test_dates": len(test_dates), "train_rows": len(train), "test_rows": len(test),
                               "run": runnable, "reason": "" if runnable else "fewer_than_8_training_dates_or_empty_test"})
            if not runnable:
                continue
            for model in MODELS:
                values, outside = predict(train, test, model)
                for row, p, extrapolation in zip(test, values, outside):
                    predictions.append({"scheme": scheme, "fold": fold, "model": model,
                        "scene_id": row["scene_id"], "date": row["overpass_group"], "station": row["station"],
                        "observed": number(row, "probe_value"), "prediction": float(p),
                        "residual_prediction_minus_observed": float(p-number(row, "probe_value")),
                        "outside_training_feature_range": bool(extrapolation)})
    summary = []
    for scheme in schemes:
        for model in MODELS:
            points = [r for r in predictions if r["scheme"] == scheme and r["model"] == model]
            if points:
                by_date = collections.defaultdict(list)
                for point in points:
                    by_date[point["date"]].append(point["prediction"]-point["observed"])
                summary.append({"scheme": scheme, "model": model,
                    "dates": len({p["date"] for p in points}),
                    **metrics([p["observed"] for p in points], [p["prediction"] for p in points]),
                    "outside_training_feature_range": sum(p["outside_training_feature_range"] for p in points),
                    "date_balanced_mae": float(np.mean([np.mean(np.abs(e)) for e in by_date.values()])),
                    "date_balanced_rmse": float(np.sqrt(np.mean([np.mean(np.array(e)**2) for e in by_date.values()]))),
                    "bootstrap": cluster_bootstrap(points)})
    return predictions, summary, fold_audit


def main():
    path = OUTPUT / "exploratory-matchups.csv"
    with path.open() as f:
        rows = list(csv.DictReader(f))
    if len({r["overpass_group"] for r in rows}) < 10:
        raise ValueError("Insufficient diagnostic dates even for exploratory models")
    predictions, summary, folds = evaluate(rows, ["leave_one_date_out", "forward_blocks", "station_and_date_holdout"])
    write_csv(OUTPUT / "exploratory-predictions.csv", predictions)
    residuals = []
    lookup = {(r["scene_id"], r["station"]): r for r in rows}
    for prediction in predictions:
        if prediction["scheme"] != "leave_one_date_out":
            continue
        row = lookup[(prediction["scene_id"], prediction["station"])]
        for name, group in [("station", row["station"]), ("season", "DJF MAM JJA SON".split()[(int(row["overpass_group"][5:7])%12)//3]),
                            ("observed_range_diagnostic", "0_to_10" if prediction["observed"] < 10 else "10_to_40"),
                            ("platform", row["platform"]), ("deployment_metadata", "before" if row["before_current_commissioned_date"] == "True" else "after")]:
            residuals.append({"dimension": name, "group": group, **prediction})
    residual_summary = []
    for key in sorted({(r["model"], r["dimension"], r["group"]) for r in residuals}):
        points = [r for r in residuals if (r["model"], r["dimension"], r["group"]) == key]
        residual_summary.append({"model": key[0], "dimension": key[1], "group": key[2],
            "dates": len({r["date"] for r in points}), **metrics([r["observed"] for r in points], [r["prediction"] for r in points])})
    associations = []
    for model in MODELS:
        for covariate in ["phycocyanin_rfu", "tile_cloud_percent", "sun_elevation", "view_angle", "red_cv"]:
            points = [r for r in predictions if r["scheme"] == "leave_one_date_out" and r["model"] == model]
            pairs = [(number(lookup[(r["scene_id"], r["station"])], covariate), r["residual_prediction_minus_observed"])
                     for r in points if lookup[(r["scene_id"], r["station"])].get(covariate) not in ["", None]]
            x, y = np.array(pairs).T if pairs else (np.array([]), np.array([]))
            associations.append({"model": model, "covariate": covariate, "n": len(pairs),
                "residual_pearson_correlation_descriptive_only": float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 and np.std(x) > 0 and np.std(y) > 0 else None})
    # Deliberately leave these as sensitivity results, not threshold optimisation.
    sensitivities = {}
    variants = {
        "post_current_commissioning_only": [r for r in rows if r["before_current_commissioned_date"] == "False"],
        "shore_buffer_200m": [r for r in rows if number(r, "footprint_shore_distance_m") >= 200],
        "shore_buffer_300m": [r for r in rows if number(r, "footprint_shore_distance_m") >= 300],
        "red_cv_max_0.1": [r for r in rows if number(r, "red_cv") <= .1],
    }
    for name, selected in variants.items():
        _, scores, _ = evaluate(selected, ["leave_one_date_out"])
        sensitivities[name] = {"rows": len(selected), "dates": len({r["overpass_group"] for r in selected}), "metrics": scores}
    report = {"status": "exploratory_only_publication_blocked", "model_version": "screening-1-no-deployable-model",
              "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "rows": len(rows), "dates": len({r["overpass_group"] for r in rows}),
              "observed_probe_range_ntu": [min(number(r, "probe_value") for r in rows), max(number(r, "probe_value") for r in rows)],
              "metrics": summary, "folds": folds, "residual_strata": residual_summary, "residual_covariates": associations, "sensitivities": sensitivities,
              "prediction_uncertainty": None,
              "limitations": ["DAERA provisional and upstream filtered; not independent validated truth", "Generic Sen2Cor BOA, no aquatic AC/glint validation",
                  "Historical deployments unresolved", "Two nearshore sites only", "Selected positive, homogeneous SCL-water subset",
                  "No final model selected, fit to full data, saved or approved", "No data-driven bands or categories validated"]}
    (OUTPUT / "exploratory-validation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    write_csv(OUTPUT / "exploratory-metrics.csv", [{k: v for k, v in score.items() if k != "bootstrap"} for score in summary])
    print(json.dumps({"rows": len(rows), "dates": report["dates"], "metrics": [{k: v for k, v in r.items() if k != "bootstrap"} for r in summary]}, indent=2))


if __name__ == "__main__":
    main()
