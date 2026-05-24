import logging
import pandas as pd
from typing import Tuple, List
from datetime import timedelta

logger = logging.getLogger(__name__)

class DataValidator:
    """
    VALIDADOR DE DATOS HISTÓRICOS - V4
    Previene backtests sobre datos corruptos o incompletos.
    """
    
    @staticmethod
    def validate(df: pd.DataFrame, symbol: str = "UNKNOWN") -> Tuple[bool, List[str]]:
        issues = []
        
        if df is None or len(df) == 0:
            return False, ["DataFrame vacío"]
        
        # 1. Columnas requeridas
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            issues.append(f"Columnas faltantes: {missing_cols}")
            return False, issues
        
        # 2. NaN values
        nan_counts = df[required_cols].isna().sum()
        if nan_counts.sum() > 0:
            for col, count in nan_counts[nan_counts > 0].items():
                issues.append(f"NaN en columna '{col}': {count} valores")
        
        # 3. Duplicados en timestamp
        if df['timestamp'].duplicated().any():
            dup_count = df['timestamp'].duplicated().sum()
            issues.append(f"Timestamps duplicados: {dup_count}")
        
        # 4. Lógica OHLC
        invalid_high = (df['high'] < df['open']) | (df['high'] < df['close']) | (df['high'] < df['low'])
        if invalid_high.any():
            issues.append(f"Lógica OHLC inválida (high < otros): {invalid_high.sum()} velas")
        
        invalid_low = (df['low'] > df['open']) | (df['low'] > df['close']) | (df['low'] > df['high'])
        if invalid_low.any():
            issues.append(f"Lógica OHLC inválida (low > otros): {invalid_low.sum()} velas")
        
        # 5. Precios no negativos
        negative_prices = (df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0) | (df['close'] <= 0)
        if negative_prices.any():
            issues.append(f"Precios negativos o cero: {negative_prices.sum()} velas")
        
        # 6. Gaps en timestamps
        if len(df) > 1:
            time_diffs = df['timestamp'].diff()
            expected_diff = timedelta(hours=1)
            large_gaps = time_diffs > expected_diff * 1.5
            if large_gaps.sum() > 0:
                gap_count = large_gaps.sum()
                largest_gap = time_diffs[large_gaps].max()
                issues.append(f"Gaps en timestamps: {gap_count} gaps, máximo: {largest_gap}")
        
        # 7. Volumen no negativo
        if (df['volume'] < 0).any():
            issues.append(f"Volumen negativo: {(df['volume'] < 0).sum()} velas")
        
        # 8. Cambios de precio irreales (>50% en una vela)
        price_changes = abs((df['close'] - df['open']) / df['open']) * 100
        unrealistic = price_changes > 50
        if unrealistic.sum() > 0:
            issues.append(f"Cambios de precio irreales (>50%): {unrealistic.sum()} velas")
        
        is_valid = len(issues) == 0
        
        if is_valid:
            logger.info(f"✅ {symbol}: Datos validados OK ({len(df)} velas)")
        else:
            logger.warning(f"⚠️  {symbol}: Datos con problemas:")
            for issue in issues:
                logger.warning(f"   - {issue}")
        
        return is_valid, issues


class BacktestValidator:
    """Validaciones específicas para evitar overfitting en backtesting"""
    
    @staticmethod
    def validate_backtest_results(results: dict) -> Tuple[bool, List[str]]:
        warnings = []
        
        pf = results.get('profit_factor', 0)
        if pf > 8.0:
            warnings.append(f"⚠️ Profit Factor muy alto: {pf:.2f} (posible overfitting)")
        
        wr = results.get('win_rate', 0)
        if wr > 90.0:
            warnings.append(f"⚠️ Win rate sospechosamente alto: {wr:.1f}% (posible overfitting)")
        
        trades = results.get('total_trades', 0)
        if trades < 10:
            warnings.append(f"⚠️ Muy pocos trades: {trades} (no es estadísticamente significativo)")
        
        is_valid = len(warnings) == 0
        return is_valid, warnings
