"""Local, explainable evidence triage model. Trained on SYNTHETIC data only.
Output is a triage aid that REQUIRES human review; never proof of wrongdoing."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURES = ["log_size", "entropy", "printable_ratio", "ext_mismatch", "double_ext", "exec_sig",
            "macro", "pdf_active", "script_hits", "metadata_missing", "ts_anomaly"]
CLASSES = ["benign", "needs_review", "suspicious"]
MODEL_VERSION = "1.0.0-synthetic"
LIMITATIONS = [
    "Trained on synthetic data generated from documented rules; it does not learn real-world attacker behaviour.",
    "Features are coarse static indicators; absence of indicators does not mean a file is safe.",
    "Confidence is a model score, not a probability of guilt or proof of wrongdoing.",
    "Every result must be reviewed by a qualified human investigator before inclusion in conclusions.",
]


def make_synthetic(n: int = 3000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        label = rng.choice(3, p=[0.55, 0.25, 0.20])
        r = {
            "log_size": rng.normal(4.5 if label < 2 else 5.0, 1.0),
            "entropy": rng.normal([4.5, 5.5, 7.0][label], 1.0 if label < 2 else 0.8),
            "printable_ratio": float(np.clip(rng.normal([0.9, 0.7, 0.4][label], 0.15), 0, 1)),
            "ext_mismatch": int(rng.random() < [0.02, 0.35, 0.55][label]),
            "double_ext": int(rng.random() < [0.0, 0.03, 0.30][label]),
            "exec_sig": int(rng.random() < [0.01, 0.10, 0.60][label]),
            "macro": int(rng.random() < [0.0, 0.15, 0.35][label]),
            "pdf_active": int(rng.poisson([0.02, 0.4, 1.2][label])),
            "script_hits": int(rng.poisson([0.05, 0.8, 4.0][label])),
            "metadata_missing": int(rng.random() < [0.10, 0.50, 0.55][label]),
            "ts_anomaly": int(rng.poisson([0.02, 0.5, 0.6][label])),
            "label": CLASSES[label],
        }
        rows.append(r)
    return pd.DataFrame(rows)


def train(model_dir, n: int = 3000, seed: int = 42) -> dict:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    df = make_synthetic(n, seed)
    X, y = df[FEATURES].values, df["label"].values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=seed, stratify=y)
    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000, C=1.0).fit(scaler.transform(Xtr), ytr)
    acc = float(accuracy_score(yte, clf.predict(scaler.transform(Xte))))
    joblib.dump({"scaler": scaler, "clf": clf}, model_dir / "model.joblib")
    card = {"version": MODEL_VERSION, "algorithm": "StandardScaler + multinomial LogisticRegression",
            "training_data": f"{n} synthetic rows (seed {seed}); no real evidence", "holdout_accuracy": round(acc, 4),
            "features": FEATURES, "classes": list(clf.classes_), "limitations": LIMITATIONS}
    (model_dir / "model_card.json").write_text(json.dumps(card, indent=2))
    return card


def load_card(model_dir) -> dict | None:
    p = Path(model_dir) / "model_card.json"
    return json.loads(p.read_text()) if p.exists() else None


def predict(model_dir, features: dict) -> dict:
    """Local inference. The joblib file is a locally trained trusted artifact; never load
    model files from untrusted sources (pickle-based)."""
    path = Path(model_dir) / "model.joblib"
    if not path.exists():
        train(model_dir)
    bundle = joblib.load(path)
    scaler, clf = bundle["scaler"], bundle["clf"]
    x = scaler.transform(np.array([[float(features.get(f, 0)) for f in FEATURES]]))
    proba = clf.predict_proba(x)[0]
    idx = int(np.argmax(proba))
    label = str(clf.classes_[idx])
    contrib = clf.coef_[idx] * x[0]
    top = sorted(zip(FEATURES, contrib, [features.get(f, 0) for f in FEATURES]), key=lambda t: -abs(t[1]))[:5]
    return {"label": label, "confidence": round(float(proba[idx]), 4),
            "probabilities": {str(c): round(float(p), 4) for c, p in zip(clf.classes_, proba)},
            "top_features": [{"feature": f, "value": round(float(v), 3), "contribution": round(float(c), 3)}
                             for f, c, v in top],
            "model_version": MODEL_VERSION, "requires_human_review": True,
            "limitations": LIMITATIONS}
