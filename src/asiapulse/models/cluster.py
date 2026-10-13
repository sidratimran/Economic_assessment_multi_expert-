"""Pattern Expert: data-driven economic profiles.

K-Means on standardised structural features. k is chosen by silhouette score (k = 4…7,
each cluster must hold ≥ 4 economies, so profiles stay policy-relevant). Cluster names are
generated from the centroid — income tier plus its most distinctive other trait — never
hard-coded, so a name always matches its members.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

FEATURES = {
    # feature: (transform, phrase-if-high, phrase-if-low)
    "gdp_pc_ppp": ("log", "High income", "Low income"),
    "growth_5y_avg": (None, "Fast-growing", "Slow-growing"),
    "emp_ratio": (None, "High employment", "Low employment"),
    "unemp": (None, "High unemployment", "Low unemployment"),
    "resource_rents": ("log1p", "Resource-rich", "Resource-light"),
    "manufacturing": (None, "Manufacturing-led", "Low manufacturing"),
    "agri_emp": (None, "Agrarian workforce", "Post-agrarian workforce"),
    "female_lfp": (None, "High female participation", "Low female participation"),
    "gov_effectiveness": (None, "Strong institutions", "Fragile institutions"),
    "internet": (None, "Digitally advanced", "Digitally lagging"),
    "tertiary_enrol": (None, "Skills-rich", "Skills-constrained"),
    "dependency": (None, "Young / high-dependency", "Working-age bulge"),
}


def _matrix(snap: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=snap.index)
    for f, (tf, *_rest) in FEATURES.items():
        v = snap.get(f, pd.Series(np.nan, index=snap.index)).astype(float)
        if tf == "log":
            v = np.log(v.clip(lower=1))
        elif tf == "log1p":
            v = np.log1p(v.clip(lower=0))
        X[f] = v.fillna(v.median())
    return X


def fit_clusters(snap: pd.DataFrame, k_range=range(4, 8), seed: int = 42, min_size: int = 4):
    X = _matrix(snap)
    Z = StandardScaler().fit_transform(X)
    trials = []
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=50, random_state=seed).fit(Z)
        sizes = np.bincount(km.labels_)
        sil = silhouette_score(Z, km.labels_)
        trials.append({"k": k, "silhouette": float(sil), "min_size": int(sizes.min()), "model": km})
    valid = [t for t in trials if t["min_size"] >= min_size] or trials
    best = max(valid, key=lambda t: t["silhouette"])
    km = best["model"]

    Zdf = pd.DataFrame(Z, index=X.index, columns=X.columns)
    labels = pd.Series(km.labels_, index=X.index)
    names = {}
    for c in sorted(labels.unique()):
        centroid = Zdf[labels == c].mean()
        inc = centroid["gdp_pc_ppp"]
        tier = "High-income" if inc > 0.6 else "Lower-income" if inc < -0.6 else "Middle-income"
        rest = centroid.drop("gdp_pc_ppp")
        f = rest.abs().idxmax()
        trait = FEATURES[f][1] if rest[f] > 0 else FEATURES[f][2]
        names[c] = f"{tier} · {trait.lower()}"
    # guarantee unique names
    seen = {}
    for c, n in names.items():
        seen[n] = seen.get(n, 0) + 1
        if seen[n] > 1:
            names[c] = f"{n} ({seen[n]})"

    pcs = PCA(n_components=2, random_state=seed).fit(Z)
    xy = pcs.transform(Z)
    out = pd.DataFrame({"cluster": labels, "cluster_name": labels.map(names),
                        "pc1": xy[:, 0], "pc2": xy[:, 1]}, index=X.index)
    meta = {
        "k": int(best["k"]), "silhouette": round(best["silhouette"], 3),
        "trials": [{"k": t["k"], "silhouette": round(t["silhouette"], 3), "min_size": t["min_size"]} for t in trials],
        "features": list(FEATURES), "explained_variance_2d": round(float(pcs.explained_variance_ratio_.sum()), 3),
        "names": {int(k): v for k, v in names.items()},
    }
    return out, Zdf, meta


def nearest_peers(iso: str, Zdf: pd.DataFrame, n: int = 5) -> list[tuple[str, float]]:
    """Nearest economies in standardised feature space (any cluster)."""
    d = np.sqrt(((Zdf - Zdf.loc[iso]) ** 2).sum(axis=1)).drop(iso)
    return [(i, float(v)) for i, v in d.sort_values().head(n).items()]
