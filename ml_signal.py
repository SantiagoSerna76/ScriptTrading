import logging
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
import joblib
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MLSignalFilter:
    """
    Machine learning filter to predict the probability that a trade signal
    will result in a winning trade.
    Loads a pre-trained model (e.g., Logistic Regression, Random Forest)
    and provides a win probability given feature vector.
    """

    def __init__(self, model_path: str = "ml_model.pkl", feature_names_path: str = "ml_feature_names.pkl"):
        self.model_path = model_path
        self.feature_names_path = feature_names_path
        self.model = None
        self.feature_names = []
        self.is_ready = False
        self._load_model()

    def _load_model(self):
        """Load pre-trained model and feature names from disk."""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.feature_names_path):
                self.model = joblib.load(self.model_path)
                self.feature_names = joblib.load(self.feature_names_path)
                self.is_ready = True
                logger.info(f"ML model loaded from {self.model_path} with {len(self.feature_names)} features.")
            else:
                logger.warning(f"ML model files not found: {self.model_path}, {self.feature_names_path}. "
                             f"ML filter will be disabled until model is trained.")
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            self.is_ready = False

    def extract_features(self,
                         df: pd.DataFrame,
                         symbol: str,
                         order_book_dict: Optional[Dict] = None,
                         mtf_dict: Optional[Dict] = None,
                         regime_info: Optional[Dict] = None) -> np.ndarray:
        """
        Extract features for ML model from current market data.
        Should match the features used during model training.

        Args:
            df: DataFrame with OHLCV and technical indicators (must include columns from strategy.calculate_indicators)
            symbol: trading symbol
            order_book_dict: output from OrderBookAnalyzer.pre_order_check() or similar
            mtf_dict: output from MultiTimeframeAnalyzer.validate_entry_with_macro()
            regime_info: output from StrategySignals.detect_market_regime()

        Returns:
            numpy array of shape (1, n_features) ready for model prediction
        """
        if df is None or len(df) == 0:
            logger.warning("Empty dataframe provided to ML feature extraction.")
            return np.zeros((1, len(self.feature_names))) if self.feature_names else np.array([])

        # Get the most recent candle
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        # Initialize feature dict
        features = {}

        # === Technical indicator features (from strategy.calculate_indicators) ===
        # Price-based
        features['close'] = last['close']
        features['returns_1'] = (last['close'] / prev['close'] - 1) if prev['close'] != 0 else 0
        features['returns_5'] = (last['close'] / df['close'].iloc[-6] - 1) if len(df) >= 6 and df['close'].iloc[-6] != 0 else 0

        # Moving averages
        if 'ema_short' in df.columns and 'ema_long' in df.columns:
            features['ema_short'] = last['ema_short']
            features['ema_long'] = last['ema_long']
            features['price_over_ema20'] = last['close'] / last['ema_short'] - 1 if last['ema_short'] != 0 else 0
            features['price_over_ema50'] = last['close'] / last['ema_long'] - 1 if last['ema_long'] != 0 else 0
            features['ema_cross'] = 1 if last['ema_short'] > last['ema_long'] else 0
            features['ema_distance'] = (last['ema_short'] - last['ema_long']) / last['ema_long'] if last['ema_long'] != 0 else 0

        # RSI
        if 'rsi' in df.columns:
            features['rsi'] = last['rsi']
            features['rsi_normalized'] = (last['rsi'] - 50) / 50  # scale to -1 to 1
            features['rsi_overbought'] = 1 if last['rsi'] > 70 else 0
            features['rsi_oversold'] = 1 if last['rsi'] < 30 else 0

        # MACD
        if 'macd' in df.columns and 'macd_signal' in df.columns:
            features['macd'] = last['macd']
            features['macd_signal'] = last['macd_signal']
            features['macd_hist'] = last['macd_hist'] if 'macd_hist' in df.columns else 0
            features['macd_bullish'] = 1 if last['macd'] > last['macd_signal'] else 0
            features['macd_hist_rising'] = 1 if len(df) >=2 and last['macd_hist'] > df['macd_hist'].iloc[-2] else 0

        # Bollinger Bands
        if 'bb_upper' in df.columns and 'bb_lower' in df.columns and 'bb_mid' in df.columns:
            features['bb_position'] = (last['close'] - last['bb_lower']) / (last['bb_upper'] - last['bb_lower']) if (last['bb_upper'] - last['bb_lower']) != 0 else 0.5
            features['bb_width'] = (last['bb_upper'] - last['bb_lower']) / last['bb_mid'] if last['bb_mid'] != 0 else 0
            features['bb_squeeze'] = 1 if features['bb_width'] < 0.1 else 0  # arbitrary threshold

        # Volume
        if 'volume' in df.columns:
            features['volume'] = last['volume']
            features['volume_sma'] = last['volume_sma'] if 'volume_sma' in df.columns else last['volume']
            features['volume_ratio'] = last['volume'] / last['volume_sma'] if last['volume_sma'] != 0 else 1
            features['volume_trend'] = (last['volume'] / df['volume_sma'].iloc[-5] - 1) if len(df) >=5 and df['volume_sma'].iloc[-5] != 0 else 0

        # ATR and volatility
        if 'atr' in df.columns:
            features['atr'] = last['atr']
            features['atr_normalized'] = last['atr'] / last['close'] if last['close'] != 0 else 0
            features['atr_change'] = (last['atr'] / prev['atr'] - 1) if prev['atr'] != 0 else 0
            features['atr_ma_ratio'] = last['atr'] / df['atr'].rolling(20).mean().iloc[-1] if len(df) >=20 and df['atr'].rolling(20).mean().iloc[-1] !=0 else 1

        # ADX
        if 'adx' in df.columns:
            features['adx'] = last['adx']
            features['adx_trend'] = 1 if last['adx'] > 25 else 0  # trend strength
            features['adx_change'] = (last['adx'] / prev['adx'] - 1) if prev['adx'] != 0 else 0

        # Stochastic
        if 'stoch_k' in df.columns and 'stoch_d' in df.columns:
            features['stoch_k'] = last['stoch_k']
            features['stoch_d'] = last['stoch_d']
            features['stoch_overbought'] = 1 if last['stoch_k'] > 80 else 0
            features['stoch_oversold'] = 1 if last['stoch_k'] < 20 else 0
            features['stoch_cross'] = 1 if last['stoch_k'] > last['stoch_d'] else 0

        # === Order Book features (solo si hay datos reales) ===
        if order_book_dict and any(v for v in order_book_dict.values() if v):
            imbalance = order_book_dict.get('imbalance', {})
            features['ob_imbalance_ratio'] = imbalance.get('imbalance_ratio', 1.0)
            features['ob_imbalance_sentiment'] = 1 if imbalance.get('sentiment') == 'BULLISH' else (-1 if imbalance.get('sentiment') == 'BEARISH' else 0)
            features['ob_buy_volume'] = imbalance.get('buy_volume', 0.0)
            features['ob_sell_volume'] = imbalance.get('sell_volume', 0.0)

            sell_wall = order_book_dict.get('sell_wall', {})
            features['ob_has_sell_wall'] = 1 if sell_wall.get('has_wall') else 0
            features['ob_sell_wall_distance'] = sell_wall.get('distance_pct', 0.0)
            features['ob_sell_wall_severity'] = {'LOW':0, 'MEDIUM':1, 'HIGH':2}.get(sell_wall.get('severity', 'LOW'), 0)

            liquidity = order_book_dict.get('liquidity', {})
            features['ob_liquidity_ok'] = 1 if liquidity.get('reason') == 'Sufficient liquidity' else 0
        else:
            logger.debug("Order Book no disponible — omitiendo features de microestructura (no se envían 0.0 falsos al modelo)")

        # === Multi-Timeframe features ===
        if mtf_dict:
            features['mtf_combined_score'] = mtf_dict.get('combined_score', 0)
            features['mtf_tactical_signal'] = 1 if mtf_dict.get('tactical_signal', False) else 0
            features['mtf_macro_valid'] = 1 if mtf_dict.get('macro_valid', False) else 0
            macro_info = mtf_dict.get('macro_info', {})
            features['mtf_macro_ema200'] = macro_info.get('ema200', 0.0)
            features['mtf_macro_adx'] = macro_info.get('adx', 0.0)
            features['mtf_macro_macd'] = macro_info.get('macd', 0.0)

        # === Regime features ===
        if regime_info:
            # One-hot encode regime (numeric only — bare 'regime' string breaks sklearn)
            regime_list = ['TREND_STRONG_BULL', 'TREND_BULL', 'TREND_WEAK', 'RANGE_VOLATILE', 'CHOPPY', 'NORMAL', 'UNKNOWN']
            for r in regime_list:
                features[f'regime_{r}'] = 1 if regime_info.get('regime') == r else 0
            features['regime_min_score'] = regime_info.get('min_score', 7)
            features['regime_adx'] = regime_info.get('adx', 0.0)

        # === Derived / interaction features ===
        # Example: price momentum vs volume
        features['price_volume'] = features.get('returns_1', 0) * features.get('volume_ratio', 1)
        # Example: volatility adjusted rsi
        features['rsi_vol_adj'] = features.get('rsi_normalized', 0) / (features.get('atr_normalized', 0.001) + 0.001)

        # Build feature vector in the order of self.feature_names
        if self.feature_names:
            feature_vector = []
            for fname in self.feature_names:
                val = features.get(fname, 0.0)
                if isinstance(val, str):
                    val = 0.0
                feature_vector.append(float(val))
            return np.array(feature_vector).reshape(1, -1)
        else:
            # If no feature names yet, return all features sorted alphabetically (for first-time training)
            # BUG-17 FIX: Filter out string values that would crash sklearn
            sorted_items = sorted(features.items())
            clean_values = []
            for k, v in sorted_items:
                if isinstance(v, str):
                    v = 0.0
                clean_values.append(float(v))
            return np.array(clean_values).reshape(1, -1)

    def is_mock_model(self) -> bool:
        """
        Detecta si el modelo cargado es un mock (entrenado con datos sintéticos).

        El modelo real se considera desplegado cuando existe el archivo
        'ml_model_trained.flag', creado automáticamente por train_real_ml_model.py
        tras un entrenamiento exitoso con datos reales.

        Mientras no exista ese flag → pass-through (no filtra trades).
        """
        if not self.is_ready or self.model is None:
            return True
        return not os.path.exists("ml_model_trained.flag")

    def predict_proba(self, features: np.ndarray) -> float:
        """
        Return probability of winning trade (class 1).
        If model not ready OR is a mock model → return 1.0 (pass-through, do not block).
        Only real models trained on ≥30 actual trades should filter signals.
        """
        if not self.is_ready or self.model is None:
            logger.debug("ML model not ready → pass-through (returning 1.0, no filtering)")
            return 1.0
        if self.is_mock_model():
            logger.debug("ML mock model detected → pass-through (returning 1.0, no filtering until real model trained)")
            return 1.0
        try:
            # Ensure 2D array
            if features.ndim == 1:
                features = features.reshape(1, -1)
            prob = self.model.predict_proba(features)[0, 1]  # probability of class 1
            return float(prob)
        except Exception as e:
            logger.error(f"Error in ML prediction: {e}")
            return 0.5

    def predict(self, features: np.ndarray, threshold: float = 0.6) -> bool:
        """
        Return True if predicted probability >= threshold.
        """
        prob = self.predict_proba(features)
        return prob >= threshold


# Example usage (for testing or offline training)
def create_training_dataset(trades_df: pd.DataFrame,
                           market_data_dict: dict,
                           order_book_dict: dict,
                           mtf_dict: dict,
                           regime_dict: dict) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Helper function to create features and labels from historical data.
    This would be run offline to train the model.

    Args:
        trades_df: DataFrame with columns ['symbol', 'entry_time', 'exit_time', 'entry_price', 'exit_price', 'pnl']
        market_data_dict: dict symbol -> DataFrame with OHLCV + indicators
        order_book_dict: dict symbol -> dict of order book features over time (complex)
        mtf_dict: dict symbol -> dict of MTF outputs over time
        regime_dict: dict symbol -> dict of regime outputs over time

    Returns:
        X: DataFrame of features
        y: Series of labels (1 if trade won, 0 if lost)
    """
    # This is a placeholder - actual implementation would loop through each trade,
    # extract features at entry time using the respective market data snapshots,
    # and label based on whether trade was profitable.
    # Due to complexity, we suggest users implement this based on their data storage.
    logger.info("Training dataset creation placeholder - implement based on your data pipeline.")
    return pd.DataFrame(), pd.Series()


if __name__ == "__main__":
    # Example of how to train and save a model (to be run offline)
    logging.basicConfig(level=logging.INFO)
    logger.info("ML Signal Filter module. To train a model, run create_training_dataset and fit a classifier.")
