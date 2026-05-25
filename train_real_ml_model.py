#!/usr/bin/env python3
"""
ENTRENAMIENTO DE MODELO ML REAL — v2
Usa los features ML guardados en el momento exacto de cada entrada (entry_features).

Mejoras sobre v1:
  - Usa los 50+ features reales (RSI, MACD, ADX, OB, MTF, regime...) en lugar de 6 básicos
  - Elimina data leakage (max_price era info del futuro)
  - Filtra cierres parciales (sub-registros duplicados)
  - Deploy automático: copia el modelo real a ml_model.pkl
  - Crea ml_model_trained.flag para activar el filtro ML en producción

Uso:
    python train_real_ml_model.py
"""

import logging
import json
import shutil
import sys
import pickle
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

try:
    from config import STRATEGY_START_TIME
except Exception:
    STRATEGY_START_TIME = None

from database import TradeDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── Archivos de salida ────────────────────────────────────────────────────────
MODEL_REAL_FILE    = "ml_model_real.pkl"
SCALER_REAL_FILE   = "ml_scaler_real.pkl"
FEATURES_FILE      = "ml_feature_names.pkl"
MODEL_DEPLOY_FILE  = "ml_model.pkl"        # archivo que usa producción
SCALER_DEPLOY_FILE = "ml_scaler.pkl"
TRAINED_FLAG       = "ml_model_trained.flag"
BLOCKED_REPORT     = "ml_training_blocked_report.json"

# ── Umbrales mínimos de calidad ───────────────────────────────────────────────
MIN_TRADES      = 30
MIN_WIN_RATE    = 0.45
MIN_PF          = 1.0
MIN_CLASS_COUNT = 5


# ─────────────────────────────────────────────────────────────────────────────
def load_training_data(db: TradeDatabase) -> list:
    """
    Carga trades cerrados que tienen entry_features guardados.
    Excluye cierres parciales para evitar duplicados.
    """
    trades = db.get_trades_with_features()
    logger.info(f"Trades con entry_features disponibles: {len(trades)}")

    # Filtro por STRATEGY_START_TIME si está configurado
    if STRATEGY_START_TIME:
        from dateutil import parser as dp
        start_ts = dp.parse(STRATEGY_START_TIME)
        before = len(trades)
        trades = [
            t for t in trades
            if t.get("entry_time") and dp.parse(t["entry_time"]) >= start_ts
        ]
        logger.info(f"Filtro STRATEGY_START_TIME: {len(trades)}/{before} trades usados")

    return trades


def validate_sample(trades: list) -> tuple:
    """Verifica que la muestra tiene calidad mínima para entrenar."""
    total  = len(trades)
    wins   = sum(1 for t in trades if (t.get("profit_loss") or 0) > 0)
    losses = total - wins
    wr     = wins / total if total else 0.0

    gross_profit = sum(t["profit_loss"] for t in trades if (t.get("profit_loss") or 0) > 0)
    gross_loss   = abs(sum(t["profit_loss"] for t in trades if (t.get("profit_loss") or 0) < 0))
    pf           = gross_profit / gross_loss if gross_loss > 0 else 999.0

    issues = []
    if total < MIN_TRADES:
        issues.append(f"Solo {total} trades con features — necesitas {MIN_TRADES}")
    if wr < MIN_WIN_RATE:
        issues.append(f"Win rate {wr*100:.1f}% < {MIN_WIN_RATE*100:.0f}% mínimo")
    if pf < MIN_PF:
        issues.append(f"Profit factor {pf:.2f} < {MIN_PF:.2f} mínimo")
    if wins < MIN_CLASS_COUNT or losses < MIN_CLASS_COUNT:
        issues.append(f"Clases insuficientes: wins={wins}, losses={losses} (mín {MIN_CLASS_COUNT} c/u)")

    quality = {
        "total": total, "wins": wins, "losses": losses,
        "win_rate": wr, "profit_factor": pf,
        "gross_profit": gross_profit, "gross_loss": gross_loss,
    }
    return len(issues) == 0, issues, quality


def build_feature_matrix(trades: list) -> tuple:
    """
    Construye la matriz X (features) e y (labels) desde los entry_features guardados.
    Usa TODOS los features que el bot calculó en el momento de la entrada.
    """
    rows, labels = [], []
    feature_names = None

    for t in trades:
        feats = t.get("entry_features", {})
        if not feats:
            continue

        # Determinar el orden canónico de features en la primera fila válida
        if feature_names is None:
            feature_names = sorted(feats.keys())

        row = [feats.get(name, 0.0) for name in feature_names]
        rows.append(row)

        label = 1 if (t.get("profit_loss") or 0) > 0 else 0
        labels.append(label)

    if not rows:
        return np.array([]), np.array([]), []

    X = np.array(rows, dtype=float)
    y = np.array(labels, dtype=int)

    # Sanity check: reemplazar NaN/inf por 0
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    logger.info(f"Matriz de features: {X.shape[0]} muestras x {X.shape[1]} features")
    logger.info(f"Labels: {y.sum()} ganancias / {(y==0).sum()} pérdidas")

    return X, y, feature_names


def train_and_evaluate(X: np.ndarray, y: np.ndarray, feature_names: list):
    """Entrena RandomForest y GradientBoosting, selecciona el mejor."""
    scaler = StandardScaler()
    X_sc   = scaler.fit_transform(X)

    n_splits = min(5, min(int(y.sum()), int((y == 0).sum())))
    n_splits = max(n_splits, 2)
    cv       = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    candidates = {
        "RandomForest": RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_split=4,
            min_samples_leaf=2, random_state=42, n_jobs=-1,
            class_weight="balanced"
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.08, max_depth=4,
            min_samples_split=4, min_samples_leaf=2,
            random_state=42, subsample=0.8
        ),
    }

    best_name, best_score, best_model = None, -1, None
    for name, model in candidates.items():
        scores = cross_val_score(model, X_sc, y, cv=cv, scoring="roc_auc")
        logger.info(f"  {name}: ROC-AUC CV = {scores.mean():.4f} (+/- {scores.std():.4f})")
        if scores.mean() > best_score:
            best_score = scores.mean()
            best_name  = name
            best_model = model

    logger.info(f"Mejor modelo: {best_name} (ROC-AUC CV={best_score:.4f})")

    # Entrenamiento final con todos los datos
    best_model.fit(X_sc, y)

    # Evaluación in-sample
    y_pred  = best_model.predict(X_sc)
    y_proba = best_model.predict_proba(X_sc)[:, 1]
    auc     = roc_auc_score(y, y_proba)

    logger.info(f"\nEvaluación in-sample (ROC-AUC = {auc:.4f}):")
    logger.info(classification_report(y, y_pred, target_names=["Pérdida", "Ganancia"]))

    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    logger.info(f"Confusion matrix: TN={tn} FP={fp} FN={fn} TP={tp}")

    # Feature importance
    if hasattr(best_model, "feature_importances_"):
        importances = best_model.feature_importances_
        ranked = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
        logger.info("Top 10 features más importantes:")
        for i, (fname, imp) in enumerate(ranked[:10], 1):
            logger.info(f"  {i:2}. {fname:<35} {imp*100:.2f}%")

    return best_model, scaler, best_name, best_score


def deploy_model(model, scaler, feature_names: list, model_name: str):
    """
    Guarda el modelo real Y lo copia a los archivos que usa producción.
    Crea ml_model_trained.flag para activar el filtro ML en el bot.
    """
    # Guardar archivos "real"
    with open(MODEL_REAL_FILE, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_REAL_FILE, "wb") as f:
        pickle.dump(scaler, f)
    with open(FEATURES_FILE, "wb") as f:
        pickle.dump(feature_names, f)

    # Deploy: copiar a los archivos que carga ml_signal.py en producción
    shutil.copy2(MODEL_REAL_FILE, MODEL_DEPLOY_FILE)
    shutil.copy2(SCALER_REAL_FILE, SCALER_DEPLOY_FILE)
    logger.info(f"Modelo desplegado: {MODEL_REAL_FILE} → {MODEL_DEPLOY_FILE}")
    logger.info(f"Scaler desplegado: {SCALER_REAL_FILE} → {SCALER_DEPLOY_FILE}")

    # Guardar metadata
    meta = {
        "model_type":   model_name,
        "n_features":   len(feature_names),
        "features":     feature_names,
        "trained_at":   datetime.now().isoformat(),
        "source":       "entry_features desde trades.db (datos reales)",
    }
    with open("ml_feature_list.json", "w") as f:
        json.dump(meta, f, indent=2)

    # Flag que activa el modelo en producción
    Path(TRAINED_FLAG).write_text(datetime.now().isoformat())
    logger.info(f"Flag de activación creado: {TRAINED_FLAG}")
    logger.info("El bot usará el modelo real en el próximo ciclo de análisis.")


def main():
    logger.info("=" * 70)
    logger.info("ENTRENAMIENTO ML REAL v2 — features desde entry_features")
    logger.info("=" * 70)

    db = TradeDatabase()

    # 1. Cargar datos
    trades = load_training_data(db)

    # 2. Validar calidad mínima
    ok, issues, quality = validate_sample(trades)

    logger.info(f"Calidad de la muestra:")
    logger.info(f"  Total trades: {quality['total']}")
    logger.info(f"  Wins/Losses:  {quality['wins']}/{quality['losses']}")
    logger.info(f"  Win Rate:     {quality['win_rate']*100:.1f}%")
    logger.info(f"  Profit Factor:{quality['profit_factor']:.2f}")

    if not ok:
        logger.warning("La muestra NO cumple los requisitos mínimos. Abortando.")
        for issue in issues:
            logger.warning(f"  -> {issue}")
        with open(BLOCKED_REPORT, "w") as f:
            json.dump({"quality": quality, "issues": issues}, f, indent=2)
        logger.info(f"Reporte guardado en {BLOCKED_REPORT}")
        return False

    # 3. Construir matriz de features
    X, y, feature_names = build_feature_matrix(trades)
    if X.size == 0:
        logger.error("No se pudieron construir features. Verifica que entry_features esté guardado en la DB.")
        return False

    # 4. Entrenar y evaluar
    logger.info("\nEntrenando modelos...")
    model, scaler, model_name, cv_score = train_and_evaluate(X, y, feature_names)

    # 5. Deploy
    logger.info("\nDesplegando modelo...")
    deploy_model(model, scaler, feature_names, model_name)

    logger.info("\n" + "=" * 70)
    logger.info(f"ENTRENAMIENTO EXITOSO — {model_name} (CV ROC-AUC={cv_score:.4f})")
    logger.info(f"El bot ya filtra trades con el modelo real.")
    logger.info("=" * 70)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
