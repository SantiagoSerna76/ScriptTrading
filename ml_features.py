import pandas as pd
import numpy as np

def extract_features(df: pd.DataFrame) -> dict:
    """
    Extrae features matemáticos avanzados para Machine Learning
    basado en el estado de la última vela (la de entrada).
    """
    if df is None or len(df) < 21:
        return {}
        
    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Z-Score (Desviación Normalizada)
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        std20 = df['close'].rolling(20).std().iloc[-1]
        z_score = (last['close'] - sma20) / std20 if std20 > 0 else 0.0
        
        # 2. Retornos Logarítmicos
        log_return = np.log(last['close'] / prev['close']) if prev['close'] > 0 else 0.0
        
        # 3. Garman-Klass Volatility (Intraday Volatility Estimator)
        # 0.5 * [ln(H/L)]^2 - (2*ln(2)-1) * [ln(C/O)]^2
        h_l = np.log(last['high'] / last['low']) if last['low'] > 0 else 0.0
        c_o = np.log(last['close'] / last['open']) if last['open'] > 0 else 0.0
        gk_vol = 0.5 * (h_l**2) - (2 * np.log(2) - 1) * (c_o**2)
        
        # 4. Encoding de Price Action (Velas Normalizadas)
        total_size = last['high'] - last['low']
        if total_size <= 0:
            total_size = 1e-9 # Evitar división por cero
            
        body_size = abs(last['close'] - last['open']) / total_size
        upper_shadow = (last['high'] - max(last['open'], last['close'])) / total_size
        lower_shadow = (min(last['open'], last['close']) - last['low']) / total_size
        
        # 5. Ratio de Volumen
        vol_sma20 = df['volume'].rolling(20).mean().iloc[-1]
        vol_ratio = last['volume'] / vol_sma20 if vol_sma20 > 0 else 0.0
        
        return {
            "z_score": float(z_score),
            "log_return": float(log_return),
            "gk_volatility": float(gk_vol),
            "body_size_pct": float(body_size),
            "upper_shadow_pct": float(upper_shadow),
            "lower_shadow_pct": float(lower_shadow),
            "vol_ratio": float(vol_ratio)
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error calculando ML features: {e}")
        return {}
