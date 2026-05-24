#!/usr/bin/env python3
"""
ENTRENAMIENTO DE MODELO ML REAL
Entrena un modelo con datos históricos REALES de trades ejecutados.

Uso:
    python train_real_ml_model.py
    
Esto cargará:
    1. Todos los trades cerrados de trades.db
    2. Extrae features en el moment de entrada
    3. Crea labels: ganancia (1) o pérdida (0)
    4. Entrena Random Forest
    5. Guarda modelo real (reemplaza mock)
"""

import sqlite3
import logging
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score, roc_curve
)
import json
import sys

try:
    from config import ENTRY_SYMBOLS, STRATEGY_START_TIME
except Exception:
    ENTRY_SYMBOLS = []
    STRATEGY_START_TIME = None

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

DB_FILE = "trades.db"
ML_MODEL_FILE = "ml_model_real.pkl"
ML_SCALER_FILE = "ml_scaler_real.pkl"
ML_FEATURES_FILE = "ml_feature_names.pkl"
FEATURE_LIST_FILE = "ml_feature_list.json"

MIN_TRAIN_TRADES = 30
MIN_TRAIN_WIN_RATE = 0.45
MIN_TRAIN_PROFIT_FACTOR = 1.0
MIN_CLASS_COUNT = 5

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────

def load_closed_trades(db_file: str) -> pd.DataFrame:
    """Carga todos los trades cerrados de la BD."""
    logger.info(f"📂 Cargando trades cerrados de {db_file}...")
    
    conn = sqlite3.connect(db_file)
    query = """
        SELECT * FROM trades 
        WHERE status = 'CLOSED' OR exit_time IS NOT NULL
        ORDER BY entry_time DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    logger.info(f"✅ Cargados {len(df)} trades cerrados")
    return df

def create_labels(df: pd.DataFrame) -> np.ndarray:
    """
    Crea labels para el modelo:
    - 1 si profit_loss > 0 (ganancia)
    - 0 si profit_loss <= 0 (pérdida)
    """
    labels = (df['profit_loss'] > 0).astype(int).values
    
    n_wins = (labels == 1).sum()
    n_losses = (labels == 0).sum()
    win_rate = 100 * n_wins / len(labels) if len(labels) > 0 else 0
    
    logger.info(f"📊 Labels creadas:")
    logger.info(f"   • Ganancias (1): {n_wins} ({win_rate:.1f}%)")
    logger.info(f"   • Pérdidas (0):  {n_losses} ({100-win_rate:.1f}%)")
    
    return labels

def calculate_trade_quality(df: pd.DataFrame) -> dict:
    """Calcula calidad mínima de la muestra antes de entrenar."""
    closed = df[df['profit_loss'].notna()].copy()
    total = len(closed)
    wins = int((closed['profit_loss'] > 0).sum()) if total else 0
    losses = total - wins
    gross_profit = float(closed.loc[closed['profit_loss'] > 0, 'profit_loss'].sum()) if total else 0.0
    gross_loss = abs(float(closed.loc[closed['profit_loss'] < 0, 'profit_loss'].sum())) if total else 0.0
    if total == 0:
        profit_factor = 0.0
    else:
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
    win_rate = wins / total if total else 0.0
    total_pl = float(closed['profit_loss'].sum()) if total else 0.0

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "total_pl": total_pl,
    }

def validate_training_sample(df: pd.DataFrame) -> tuple:
    """Bloquea entrenamiento si la muestra real no tiene calidad mínima."""
    quality = calculate_trade_quality(df)
    issues = []

    if quality["total_trades"] < MIN_TRAIN_TRADES:
        issues.append(f"menos de {MIN_TRAIN_TRADES} trades cerrados")
    if quality["win_rate"] < MIN_TRAIN_WIN_RATE:
        issues.append(
            f"win rate {quality['win_rate']*100:.1f}% < {MIN_TRAIN_WIN_RATE*100:.0f}%"
        )
    if quality["profit_factor"] < MIN_TRAIN_PROFIT_FACTOR:
        issues.append(
            f"profit factor {quality['profit_factor']:.2f} < {MIN_TRAIN_PROFIT_FACTOR:.2f}"
        )
    if quality["wins"] < MIN_CLASS_COUNT or quality["losses"] < MIN_CLASS_COUNT:
        issues.append(
            f"clases insuficientes: wins={quality['wins']}, losses={quality['losses']} "
            f"(mínimo {MIN_CLASS_COUNT} por clase)"
        )

    return len(issues) == 0, issues, quality

def extract_technical_features(df: pd.DataFrame) -> dict:
    """
    Extrae features técnicos BASICOS de los trades.
    
    Nota: Para un modelo más robusto, idealmente necesitarías
    tener guardados los datos OHLCV en el momento de entrada.
    
    Por ahora usamos lo que tenemos disponible.
    """
    features = {}
    
    # Features basados en precios
    features['entry_price'] = df['entry_price'].values
    features['entry_quantity'] = df['entry_quantity'].values
    features['max_price'] = df['max_price'].fillna(0).values
    
    # Features basados en SL/TP
    features['sl_distance_pct'] = (
        (df['entry_price'] - df['stop_loss']) / df['entry_price'] * 100
    ).values
    features['tp_distance_pct'] = (
        (df['take_profit'] - df['entry_price']) / df['entry_price'] * 100
    ).values
    
    # Ratio de riesgo/recompensa
    features['risk_reward_ratio'] = (
        features['tp_distance_pct'] / (features['sl_distance_pct'] + 0.001)
    )
    
    # Profit/Loss percent (pero NO lo usamos como input, solo como label)
    # features['profit_percent'] = df['profit_percent'].fillna(0).values
    
    return features

def create_feature_matrix(df: pd.DataFrame) -> tuple:
    """
    Crea matriz de features para el modelo.
    
    Retorna:
        X: matriz de features (n_samples, n_features)
        feature_names: lista de nombres de features
    """
    logger.info("🔧 Extrayendo features...")
    
    features = extract_technical_features(df)
    
    # Convertir dict a DataFrame
    X = pd.DataFrame(features)
    
    # Remover filas con NaN
    X = X.fillna(0)
    
    feature_names = list(X.columns)
    
    logger.info(f"✅ Features extraídas: {len(feature_names)}")
    for i, name in enumerate(feature_names, 1):
        logger.info(f"   {i}. {name}")
    
    return X.values, feature_names

def train_model(X: np.ndarray, y: np.ndarray, feature_names: list):
    """
    Entrena un modelo Random Forest con validación cruzada.
    """
    logger.info("\n🤖 Entrenando modelo Random Forest...")
    
    # Estandarizar features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Validación cruzada
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    # Modelo 1: Random Forest
    logger.info("   [1/2] Random Forest...")
    rf_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced'  # Maneja desbalance de clases
    )
    
    rf_scores = cross_val_score(rf_model, X_scaled, y, cv=cv, scoring='roc_auc')
    logger.info(f"      Random Forest ROC-AUC CV: {rf_scores.mean():.4f} (+/- {rf_scores.std():.4f})")
    
    # Modelo 2: Gradient Boosting (alternativa más potente)
    logger.info("   [2/2] Gradient Boosting...")
    gb_model = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        subsample=0.8
    )
    
    gb_scores = cross_val_score(gb_model, X_scaled, y, cv=cv, scoring='roc_auc')
    logger.info(f"      Gradient Boosting ROC-AUC CV: {gb_scores.mean():.4f} (+/- {gb_scores.std():.4f})")
    
    # Seleccionar mejor modelo
    if gb_scores.mean() > rf_scores.mean():
        logger.info("✅ Gradient Boosting es mejor. Usando GB como modelo final.")
        best_model = gb_model
        best_score = gb_scores.mean()
        model_name = "GradientBoosting"
    else:
        logger.info("✅ Random Forest es mejor. Usando RF como modelo final.")
        best_model = rf_model
        best_score = rf_scores.mean()
        model_name = "RandomForest"
    
    # Entrenar modelo final con TODO el dataset
    logger.info(f"\n📌 Entrenando modelo final ({model_name}) con {len(X)} samples...")
    best_model.fit(X_scaled, y)
    
    logger.info(f"✅ Modelo entrenado. ROC-AUC esperado: {best_score:.4f}")
    
    return best_model, scaler, model_name, best_score

def evaluate_model(model, scaler: StandardScaler, X: np.ndarray, y: np.ndarray):
    """
    Evalúa el modelo en el dataset de entrenamiento.
    (No es ideal, pero mejor que nada sin test set separado)
    """
    logger.info("\n📊 Evaluando modelo...")
    
    X_scaled = scaler.transform(X)
    y_pred = model.predict(X_scaled)
    y_pred_proba = model.predict_proba(X_scaled)[:, 1]
    
    # ROC-AUC
    auc_score = roc_auc_score(y, y_pred_proba)
    logger.info(f"   ROC-AUC Score: {auc_score:.4f}")
    
    # Classification Report
    logger.info("\n   Classification Report:")
    report = classification_report(y, y_pred, target_names=['Pérdida', 'Ganancia'])
    logger.info(report)
    
    # Confusion Matrix
    cm = confusion_matrix(y, y_pred)
    tn, fp, fn, tp = cm.ravel()
    logger.info(f"\n   Confusion Matrix:")
    logger.info(f"      True Negatives:  {tn} (Pérdidas predichas correctamente)")
    logger.info(f"      False Positives: {fp} (Ganancias predichas pero fueron pérdidas)")
    logger.info(f"      False Negatives: {fn} (Pérdidas predichas pero fueron ganancias)")
    logger.info(f"      True Positives:  {tp} (Ganancias predichas correctamente)")
    
    # Feature Importance (si el modelo lo soporta)
    if hasattr(model, 'feature_importances_'):
        logger.info(f"\n   Top 5 Features Importantes:")
        # ... (implementar después si es necesario)
    
    return auc_score

def save_model(model, scaler: StandardScaler, feature_names: list, model_name: str):
    """Guarda el modelo entrenado y el scaler."""
    logger.info("\n💾 Guardando modelo...")
    
    # Guardar modelo
    with open(ML_MODEL_FILE, 'wb') as f:
        pickle.dump(model, f)
    logger.info(f"   ✅ Modelo guardado: {ML_MODEL_FILE}")
    
    # Guardar scaler
    with open(ML_SCALER_FILE, 'wb') as f:
        pickle.dump(scaler, f)
    logger.info(f"   ✅ Scaler guardado: {ML_SCALER_FILE}")
    
    # Guardar nombres de features
    with open(ML_FEATURES_FILE, 'wb') as f:
        pickle.dump(feature_names, f)
    logger.info(f"   ✅ Feature names guardados: {ML_FEATURES_FILE}")
    
    # Guardar lista de features como JSON (legible)
    feature_info = {
        "model_type": model_name,
        "n_features": len(feature_names),
        "features": feature_names,
        "timestamp": datetime.now().isoformat(),
        "source": "trades.db (datos reales)"
    }
    with open(FEATURE_LIST_FILE, 'w') as f:
        json.dump(feature_info, f, indent=2)
    logger.info(f"   ✅ Feature info guardado: {FEATURE_LIST_FILE}")

def walk_forward_split(df, train_pct=0.75):
    """Split temporal para walk-forward validation."""
    df_sorted = df.sort_values('entry_time')
    n = len(df_sorted)
    n_train = int(n * train_pct)
    idx = df_sorted.index
    train_idx = idx[:n_train]
    test_idx = idx[n_train:]
    return df_sorted.loc[train_idx], df_sorted.loc[test_idx]

def feature_importance_table(model, feature_names):
    if not hasattr(model, 'feature_importances_'):
        logger.warning("El modelo no soporta feature_importances_ (solo RF/GB)")
        return None
    importances = model.feature_importances_
    total = np.sum(importances)
    rel_importances = 100 * importances / total if total > 0 else importances
    ranked = sorted(zip(feature_names, rel_importances), key=lambda x: x[1], reverse=True)
    logger.info("\n📝 Importancia de Variables:")
    logger.info(f"{'Rank':<6}{'Feature':<25}{'Weight_%':>10}")
    for i, (f, imp) in enumerate(ranked, 1):
        logger.info(f"{i:<6}{f:<25}{imp:>10.2f}")
    return ranked

def prune_features(ranked_importances, min_pct=1.0):
    keep = [name for name, imp in ranked_importances if imp >= min_pct]
    prune = [name for name, imp in ranked_importances if imp < min_pct]
    return keep, prune

def main():
    logger.info("=" * 80)
    logger.info("ENTRENAMIENTO DE MODELO ML REAL - WALK FORWARD AUDITORÍA")
    logger.info("=" * 80)

    # 1. Cargar datos
    df_trades = load_closed_trades(DB_FILE)

    if ENTRY_SYMBOLS and 'symbol' in df_trades.columns:
        before = len(df_trades)
        df_trades = df_trades[df_trades['symbol'].isin(ENTRY_SYMBOLS)].copy()
        logger.info(
            f"🎯 Filtrando entrenamiento a ENTRY_SYMBOLS={ENTRY_SYMBOLS}: "
            f"{len(df_trades)}/{before} trades usados"
        )

    if STRATEGY_START_TIME and 'entry_time' in df_trades.columns:
        before = len(df_trades)
        start_ts = pd.to_datetime(STRATEGY_START_TIME)
        df_trades = df_trades[pd.to_datetime(df_trades['entry_time'], errors='coerce') >= start_ts].copy()
        logger.info(
            f"🕒 Filtrando entrenamiento desde STRATEGY_START_TIME={STRATEGY_START_TIME}: "
            f"{len(df_trades)}/{before} trades usados"
        )

    logger.info("\n📊 RESUMEN DE TRADES EXISTENTES EN TRADES.DB:")
    logger.info(f"  Total de registros (trades) encontrados: {len(df_trades)}")
    sample_ok, sample_issues, sample_quality = validate_training_sample(df_trades)
    logger.info(f"  Ganadores/perdedores: {sample_quality['wins']}/{sample_quality['losses']}")
    logger.info(f"  Win rate real: {sample_quality['win_rate']*100:.1f}%")
    logger.info(f"  Profit factor real: {sample_quality['profit_factor']:.2f}")
    logger.info(f"  P&L real total: ${sample_quality['total_pl']:.2f}")

    if not sample_ok:
        logger.warning("⚠️ La muestra NO pasa los guardrails de calidad. NO se entrenará todavía.")
        for issue in sample_issues:
            logger.warning(f"   - {issue}")
        with open("ml_training_blocked_report.json", "w", encoding="utf-8") as f:
            json.dump({"quality": sample_quality, "issues": sample_issues}, f, indent=2)
        logger.warning("📝 Reporte guardado en ml_training_blocked_report.json")
        return False

    logger.info(f"\n📈 Resumen de datos:")
    logger.info(f"   Total trades: {len(df_trades)}")
    logger.info(f"   Win rate: {(df_trades['profit_loss'] > 0).sum() / len(df_trades) * 100:.1f}%")
    logger.info(f"   ROI total: {df_trades['profit_percent'].sum():.2f}%")

    # Split walk-forward
    train_df, test_df = walk_forward_split(df_trades)
    logger.info(f"Entrenamiento: {len(train_df)} trades | Test futuro: {len(test_df)} trades")

    # 2. Crear labels
    y_train = create_labels(train_df)
    y_test  = create_labels(test_df)

    # 3. Extraer features
    X_train, feature_names = create_feature_matrix(train_df)
    X_test, feature_names_test = create_feature_matrix(test_df)

    # 4. Entrenar modelo con train set
    model, scaler, model_name, cv_score = train_model(X_train, y_train, feature_names)

    # 5. Evaluar modelo en train y TEST (futuro)
    logger.info("\n== Evaluación In-Sample (Train) ==")
    train_auc = evaluate_model(model, scaler, X_train, y_train)
    logger.info("\n== Evaluación Walk-Forward (FUTURO) ==")
    test_auc = evaluate_model(model, scaler, X_test, y_test)

    # 6. Tabla de importancia de features
    ranked_imp = feature_importance_table(model, feature_names)
    if ranked_imp is None:
        ranked_imp = [(f, 0) for f in feature_names]

    # 7. Exportar tabla de importancias a CSV
    import csv
    with open("feature_importance.csv", "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Rank", "Feature", "Importance_%"])
        for i, (name, weight) in enumerate(ranked_imp, 1):
            writer.writerow([i, name, round(weight, 4)])
    logger.info("✅ Tabla de importancia exportada a feature_importance.csv")

    # 8. Pruning only as RECOMMENDATION, not execution
    keep_features, prune_features_list = prune_features(ranked_imp)
    logger.info(f"\n🌱 Features que SE RECOMIENDA eliminar (importancia <1%): {prune_features_list}")
    logger.info(f"🌿 Features recomendadas para mantener: {keep_features}")
    with open("pruned_features.json", "w") as f:
        json.dump({"features_recommended_remove": prune_features_list, "features_keep": keep_features}, f, indent=2)
        logger.info("   📝 Informe de poda RECOMENDADA guardado en pruned_features.json")

    logger.info("""
********************************************************************************
 AUDITORÍA COMPLETA: NO SE REALIZÓ ENTRENAMIENTO FINAL NI PRUNING AÚN.
 Revisa los resultados en:
   - feature_importance.csv (importancia de variables para Excel/VS Code)
   - pruned_features.json (reporte recomendación de pruning)
 Cuando lo apruebes, puedes pedir que se re-entrene SOLO con las features clave.
********************************************************************************
""")

    logger.info("\n" + "=" * 80)
    logger.info("✅ AUDITORÍA FINALIZADA WALK-FORWARD - NINGÚN CAMBIO DE MODELO REALIZADO")
    logger.info("=" * 80)
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
