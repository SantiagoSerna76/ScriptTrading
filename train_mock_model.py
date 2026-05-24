"""
Script to create and save a mock ML model for testing the integration.
In practice, you would replace this with actual training on historical data.
"""
import logging
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import joblib
import os

def create_and_save_mock_model():
    """Create a mock trained model and save it to disk."""
    logger.info("Creating mock ML model for testing...")
    
    # Create mock feature names (should match what MLSignalFilter.extract_features produces)
    # These are the key features we expect to extract
    feature_names = [
        'close', 'returns_1', 'returns_5',
        'ema_short', 'ema_long', 'price_over_ema20', 'price_over_ema50', 
        'ema_cross', 'ema_distance',
        'rsi', 'rsi_normalized', 'rsi_overbought', 'rsi_oversold',
        'macd', 'macd_signal', 'macd_hist', 'macd_bullish', 'macd_hist_rising',
        'bb_position', 'bb_width', 'bb_squeeze',
        'volume', 'volume_sma', 'volume_ratio', 'volume_trend',
        'atr', 'atr_normalized', 'atr_change', 'atr_ma_ratio',
        'adx', 'adx_trend', 'adx_change',
        'stoch_k', 'stoch_d', 'stoch_overbought', 'stoch_oversold', 'stoch_cross',
        'ob_imbalance_ratio', 'ob_imbalance_sentiment', 'ob_buy_volume', 'ob_sell_volume',
        'ob_has_sell_wall', 'ob_sell_wall_distance', 'ob_sell_wall_severity',
        'ob_liquidity_ok',
        'mtf_combined_score', 'mtf_tactical_signal', 'mtf_macro_valid',
        'mtf_macro_ema200', 'mtf_macro_adx', 'mtf_macro_macd',
        'regime_TREND_STRONG_BULL', 'regime_TREND_BULL', 'regime_TREND_WEAK',
        'regime_RANGE_VOLATILE', 'regime_CHOPPY', 'regime_NORMAL', 'regime_UNKNOWN',
        'regime_min_score', 'regime_adx',
        'price_volume', 'rsi_vol_adj'
    ]
    
    # Generate mock training data
    # In reality, this would be hundreds/thousands of historical examples
    np.random.seed(42)
    n_samples = 1000
    
    # Generate features that have some predictive power
    X = np.random.randn(n_samples, len(feature_names))
    
    # Create labels with some dependence on features
    # Example: higher probability of winning when:
    # - price is rising (returns_1 > 0)
    # - RSI is not extreme (not overbought/oversold)
    # - MACD is bullish
    # - volume is increasing
    # - not near sell wall
    # - in trending regime
    
    # Create a simple scoring function
    score = (
        0.3 * np.clip(X[:, feature_names.index('returns_1')], -1, 1) +  # returns
        0.2 * (1 - np.abs(X[:, feature_names.index('rsi_normalized')])) +  # RSI near 50
        0.2 * X[:, feature_names.index('macd_bullish')] +  # MACD bullish
        0.1 * np.clip(X[:, feature_names.index('volume_ratio')], 0, 2) +  # volume
        -0.2 * X[:, feature_names.index('ob_has_sell_wall')] +  # avoid sell walls
        0.2 * X[:, feature_names.index('regime_TREND_STRONG_BULL')] +  # strong trend
        0.1 * X[:, feature_names.index('mtf_combined_score')] / 10.0  # MTF score
    )
    
    # Convert to probability and then to binary labels
    prob = 1 / (1 + np.exp(-score))  # sigmoid
    y = (np.random.rand(n_samples) < prob).astype(int)
    
    # Train a simple logistic regression model
    model = LogisticRegression(random_state=42, max_iter=1000)
    model.fit(X, y)
    
    # Calculate training accuracy
    train_acc = model.score(X, y)
    logger.info(f"Mock model training accuracy: {train_acc:.3f}")
    
    # Save model and feature names
    model_path = "ml_model.pkl"
    feature_names_path = "ml_feature_names.pkl"
    
    joblib.dump(model, model_path)
    joblib.dump(feature_names, feature_names_path)
    
    logger.info(f"Mock model saved to {model_path}")
    logger.info(f"Feature names saved to {feature_names_path}")
    
    # Show top 5 feature coefficients for interpretation
    if hasattr(model, 'coef_'):
        coefs = model.coef_[0]
        top_indices = np.argsort(np.abs(coefs))[::-1][:5]
        logger.info("Top 5 features by coefficient magnitude:")
        for idx in top_indices:
            logger.info(f"  {feature_names[idx]}: {coefs[idx]:.4f}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    logger = logging.getLogger(__name__)
    create_and_save_mock_model()