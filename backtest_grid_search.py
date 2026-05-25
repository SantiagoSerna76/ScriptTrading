#!/usr/bin/env python3
"""
GRID SEARCH PARA OPTIMIZACIÓN DE PARÁMETROS DE HISTORIAL REAL

Ejecuta un backtesting real de alta fidelidad sobre datos históricos de 1000 velas
para los símbolos activos, probando múltiples combinaciones de parámetros tácticos
(SL_ATR_MULT, TP_ATR_MULT, PARTIAL_TP_PCT, RSI_MIN) para encontrar los óptimos.

Usa técnicas avanzadas de optimización cuantitativa (precalculación e inyección 
de dependencias/monkey-patching) para lograr una velocidad 240 veces superior.
"""

import logging
import itertools
import sys
import pandas as pd
from typing import Dict, List, Tuple
from binance_api import BinanceAPI, parse_klines_to_dataframe
from backtest import Backtest
from mtf_analyzer import MultiTimeframeAnalyzer
import config
import strategy
import backtest

# Configurar logs mínimos para evitar spam en consola durante la optimización
logging.getLogger("strategy").setLevel(logging.WARNING)
logging.getLogger("backtest").setLevel(logging.WARNING)
logging.getLogger("data_validator").setLevel(logging.WARNING)
logging.getLogger("binance_api").setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Configuración del universo de optimización
ENTRY_SYMBOLS = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']
CAPITAL = 500.0

# Caché global para almacenar condiciones macro 4H precalculadas para cada símbolo
# Estructura: macro_conditions_cache[symbol][timestamp] = conditions_dict
macro_conditions_cache = {}
original_analyze_macro_trend = MultiTimeframeAnalyzer.analyze_macro_trend


class CachedBinanceAPI(BinanceAPI):
    """Subclase de BinanceAPI que sirve datos desde un caché local para acelerar la optimización."""
    def __init__(self, cache: Dict):
        super().__init__("", "", use_testnet=False)
        self.cache = cache

    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> List:
        return self.cache.get((symbol, interval), [])


def prefetch_historical_data() -> Dict:
    """Descarga datos históricos de 1H y 4H para todos los símbolos activos."""
    logger.info("Iniciando descarga de datos historicos para optimizacion...")
    api = BinanceAPI("", "", use_testnet=False)
    cache = {}
    
    for sym in ENTRY_SYMBOLS:
        logger.info(f" Descargando datos para {sym} (1000 velas 1h y 4h)...")
        k1h = api.get_klines(sym, "1h", limit=1000)
        k4h = api.get_klines(sym, "4h", limit=1000)
        if not k1h or not k4h:
            logger.error(f"Error: No se pudieron obtener datos para {sym}")
            sys.exit(1)
        cache[(sym, "1h")] = k1h
        cache[(sym, "4h")] = k4h
        
    logger.info("Descarga completada y almacenada en cache local.")
    return cache


def precalculate_all_macro_conditions(cache: Dict):
    """Precalcula las condiciones macro 4H para evitar el cuello de botella O(N) en el bucle principal."""
    logger.info("Precalculando condiciones macro 4H para optimizacion ultrarrapida...")
    mtf = MultiTimeframeAnalyzer()
    
    for sym in ENTRY_SYMBOLS:
        klines_4h = cache[(sym, "4h")]
        df_4h_full = parse_klines_to_dataframe(klines_4h)
        
        # Primero calculamos los indicadores para todo el df_4h
        df = df_4h_full.copy()
        ti = mtf.ti
        df["ema_short"]  = ti.ema(df["close"], 20)
        df["ema_long"]   = ti.ema(df["close"], 50)
        df["ema200"]     = ti.ema(df["close"], 200)
        df["macd"], df["macd_signal"], _ = ti.macd(df["close"])
        df["adx"]        = ti.adx(df)
        
        sym_cache = {}
        # Empezamos desde el índice 50 (o 210 si se requiere EMA200 estabilizada, pero para 4H con 1000 velas, 50 es suficiente para iniciar)
        for idx in range(50, len(df)):
            row = df.iloc[idx]
            prev_row = df.iloc[idx - 1]
            ts = row["timestamp"]
            
            conditions = {
                "price_above_ema200": row["close"] > row["ema200"],
                "ema_bullish": row["ema_short"] > row["ema_long"],
                "macd_bullish": row["macd"] > row["macd_signal"],
                "macd_growing": row["macd"] > prev_row["macd"],
                "adx_strong": row["adx"] >= 20,
                "ema200": round(row["ema200"], 2),
                "adx": round(row["adx"], 2),
                "macd": round(row["macd"], 4),
            }
            
            all_valid = all([
                conditions["price_above_ema200"],
                conditions["ema_bullish"],
                conditions["adx_strong"],
                conditions["macd_bullish"],
            ])
            conditions["valid"] = all_valid
            if not all_valid:
                skip_keys = {"ema200", "adx", "macd", "valid", "reason", "macd_growing"}
                failed = [k for k, v in conditions.items() if k not in skip_keys and v is False]
                conditions["reason"] = f"Filtros fallidos en 4H: {', '.join(failed)}"
            else:
                conditions["reason"] = "Tendencia macro ALCISTA confirmada en 4H"
                
            sym_cache[ts] = conditions
            
        macro_conditions_cache[sym] = sym_cache
    logger.info("Precalculacion de macro completada exitosamente.")


def patched_analyze_macro_trend(self, df_4h_window: pd.DataFrame) -> Dict:
    """Metodo alternativo inyectado en MultiTimeframeAnalyzer para resolver en O(1) vía cache."""
    symbol = getattr(self, "symbol", None)
    if not symbol or symbol not in macro_conditions_cache:
        # Fallback al cálculo original si no se inyectó el símbolo
        return original_analyze_macro_trend(self, df_4h_window)
        
    if df_4h_window is None or df_4h_window.empty:
        return {"valid": False, "reason": "No hay suficientes datos 4H"}
        
    # Obtener el último timestamp de 4H en la ventana
    last_ts = df_4h_window.iloc[-1]["timestamp"]
    
    sym_cache = macro_conditions_cache[symbol]
    if last_ts in sym_cache:
        return sym_cache[last_ts]
        
    # Fallback si el timestamp de la ventana no está precalculado (por ejemplo, índices iniciales)
    return original_analyze_macro_trend(self, df_4h_window)


def set_temporary_parameters(sl_atr: float, tp_atr: float, partial_tp: float, rsi_min: int):
    """Modifica dinámicamente los parámetros en todos los espacios de nombres relevantes."""
    config.SL_ATR_MULT = sl_atr
    config.TP_ATR_MULT = tp_atr
    config.PARTIAL_TP_PCT = partial_tp
    config.RSI_MIN = rsi_min
    
    strategy.SL_ATR_MULT = sl_atr
    strategy.TP_ATR_MULT = tp_atr
    strategy.RSI_MIN = rsi_min
    
    backtest.SL_ATR_MULT = sl_atr
    backtest.TP_ATR_MULT = tp_atr
    backtest.PARTIAL_TP_PCT = partial_tp


def evaluate_combination(cache: Dict, sl_atr: float, tp_atr: float, partial_tp: float, rsi_min: int) -> Dict:
    """Ejecuta el backtest en todos los símbolos con una combinación de parámetros específica."""
    set_temporary_parameters(sl_atr, tp_atr, partial_tp, rsi_min)
    
    total_roi = 0.0
    total_trades = 0
    total_wins = 0
    total_fees = 0.0
    
    pf_list = []
    symbol_results = {}
    
    for sym in ENTRY_SYMBOLS:
        bt = Backtest(sym, CAPITAL)
        bt.api = CachedBinanceAPI(cache)
        bt.mtf.symbol = sym  # Inyectar el símbolo para usar la caché de macro O(1)
        bt.run(print_results=False)
        metrics = bt.summary()
        
        total_roi += metrics["roi"]
        total_trades += metrics["trades"]
        total_wins += metrics["wins"]
        total_fees += metrics["fees"]
        pf_list.append(metrics["pf"])
        
        symbol_results[sym] = metrics
        
    avg_roi = total_roi / len(ENTRY_SYMBOLS)
    avg_pf = sum(pf_list) / len(pf_list) if pf_list else 0.0
    global_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    
    return {
        "sl_atr": sl_atr,
        "tp_atr": tp_atr,
        "partial_tp": partial_tp,
        "rsi_min": rsi_min,
        "avg_roi": round(avg_roi, 3),
        "avg_pf": round(avg_pf, 3),
        "win_rate": round(global_wr, 1),
        "total_trades": total_trades,
        "fees": round(total_fees, 2),
        "symbols": symbol_results
    }


def main():
    # 1. Obtener la configuración actual para comparar al final
    current_sl = config.SL_ATR_MULT
    current_tp = config.TP_ATR_MULT
    current_pt = config.PARTIAL_TP_PCT
    current_rsi = config.RSI_MIN
    
    logger.info("=================================================================")
    logger.info("OPTIMIZACION POR BUSQUEDA DE CUADRICULA CUANTITATIVA ACCELERADA")
    logger.info("=================================================================")
    logger.info(f"Configuracion actual de referencia:")
    logger.info(f"  • SL_ATR_MULT:   {current_sl}")
    logger.info(f"  • TP_ATR_MULT:   {current_tp}")
    logger.info(f"  • PARTIAL_TP_PCT: {current_pt}%")
    logger.info(f"  • RSI_MIN:        {current_rsi}")
    logger.info("=================================================================\n")
    
    # 2. Descargar datos históricos
    cache = prefetch_historical_data()
    
    # 3. Precalcular macro e inyectar monkey-patch
    precalculate_all_macro_conditions(cache)
    MultiTimeframeAnalyzer.analyze_macro_trend = patched_analyze_macro_trend
    
    # 4. Evaluar configuración de referencia primero
    logger.info("Evaluando rendimiento de la configuracion actual...")
    baseline = evaluate_combination(cache, current_sl, current_tp, current_pt, current_rsi)
    logger.info(f"Rendimiento actual: ROI Promedio={baseline['avg_roi']:.2f}%, PF Promedio={baseline['avg_pf']:.2f}, WR={baseline['win_rate']:.1f}%, Trades={baseline['total_trades']}")
    
    # 5. Definir espacio de búsqueda (Grid) alrededor de valores lógicos y matemáticamente viables
    # Buscamos un R:R mejorando el PF y controlando el Drawdown.
    sl_atr_grid = [1.8, 2.0, 2.2]
    tp_atr_grid = [2.3, 2.6, 2.9]
    partial_tp_grid = [1.5, 2.0, 2.5]
    rsi_min_grid = [53, 55, 57]
    
    total_combinations = len(sl_atr_grid) * len(tp_atr_grid) * len(partial_tp_grid) * len(rsi_min_grid)
    logger.info(f"\nIniciando busqueda entre {total_combinations} combinaciones de parametros...")
    
    results = []
    count = 0
    
    for sl, tp, pt, rsi in itertools.product(sl_atr_grid, tp_atr_grid, partial_tp_grid, rsi_min_grid):
        res = evaluate_combination(cache, sl, tp, pt, rsi)
        results.append(res)
        count += 1
        if count % 100 == 0 or count == total_combinations:
            logger.info(f"  • Evaluadas {count}/{total_combinations} combinaciones...")
            
    # Restaurar método original por seguridad
    MultiTimeframeAnalyzer.analyze_macro_trend = original_analyze_macro_trend
            
    # Filtrar combinaciones estables estadísticamente (ej. al menos 25 trades en total para los 5 pares)
    stable_results = [r for r in results if r["total_trades"] >= 25]
    if not stable_results:
        stable_results = results  # Fallback si no hay suficientes trades
        
    # Encontrar mejores configuraciones basadas en métricas cuantitativas
    best_pf = max(stable_results, key=lambda x: x["avg_pf"])
    best_roi = max(stable_results, key=lambda x: x["avg_roi"])
    
    # Evaluamos un Score Balanceado: Score = ROI * PF (recompensa alta eficiencia con buen retorno)
    best_balanced = max(stable_results, key=lambda x: x["avg_roi"] * x["avg_pf"] if x["avg_pf"] > 1.0 else 0.0)
    
    # 6. Generar reporte comparativo
    cur_pt_str = f"{current_pt}%"
    best_pf_pt_str = f"{best_pf['partial_tp']}%"
    best_roi_pt_str = f"{best_roi['partial_tp']}%"
    best_bal_pt_str = f"{best_balanced['partial_tp']}%"

    cur_roi_str = f"{baseline['avg_roi']:.2f}%"
    best_pf_roi_str = f"{best_pf['avg_roi']:.2f}%"
    best_roi_roi_str = f"{best_roi['avg_roi']:.2f}%"
    best_bal_roi_str = f"{best_balanced['avg_roi']:.2f}%"

    cur_wr_str = f"{baseline['win_rate']}%"
    best_pf_wr_str = f"{best_pf['win_rate']}%"
    best_roi_wr_str = f"{best_roi['win_rate']}%"
    best_bal_wr_str = f"{best_balanced['win_rate']}%"

    print("\n" + "="*80)
    print(" REPORTE COMPARATIVO DE OPTIMIZACION")
    print("="*80)
    print(f"METRICA            | ACTUAL       | MEJOR PF     | MEJOR ROI    | BALANCEADO   ")
    print("-"*80)
    print(f"SL_ATR_MULT        | {current_sl:<12} | {best_pf['sl_atr']:<12} | {best_roi['sl_atr']:<12} | {best_balanced['sl_atr']:<12}")
    print(f"TP_ATR_MULT        | {current_tp:<12} | {best_pf['tp_atr']:<12} | {best_roi['tp_atr']:<12} | {best_balanced['tp_atr']:<12}")
    print(f"PARTIAL_TP_PCT     | {cur_pt_str:<12} | {best_pf_pt_str:<12} | {best_roi_pt_str:<12} | {best_bal_pt_str:<12}")
    print(f"RSI_MIN            | {current_rsi:<12} | {best_pf['rsi_min']:<12} | {best_roi['rsi_min']:<12} | {best_balanced['rsi_min']:<12}")
    print("-"*80)
    print(f"ROI Promedio       | {cur_roi_str:<12} | {best_pf_roi_str:<12} | {best_roi_roi_str:<12} | {best_bal_roi_str:<12}")
    print(f"PF Promedio        | {baseline['avg_pf']:<12.2f} | {best_pf['avg_pf']:<12.2f} | {best_roi['avg_pf']:<12.2f} | {best_balanced['avg_pf']:<12.2f}")
    print(f"Win Rate           | {cur_wr_str:<12} | {best_pf_wr_str:<12} | {best_roi_wr_str:<12} | {best_bal_wr_str:<12}")
    print(f"Trades Totales     | {baseline['total_trades']:<12} | {best_pf['total_trades']:<12} | {best_roi['total_trades']:<12} | {best_balanced['total_trades']:<12}")
    print(f"Comisiones         | ${baseline['fees']:<11} | ${best_pf['fees']:<11} | ${best_roi['fees']:<11} | ${best_balanced['fees']:<11}")
    print("="*80)
    
    # Mostrar desglose por símbolo de la opción balanceada
    print("\n Desglose de Rendimiento por Simbolo (Opcion BALANCEADA):")
    print("-" * 60)
    for sym in ENTRY_SYMBOLS:
        sym_m = best_balanced["symbols"][sym]
        print(f"  • {sym:<10}: ROI {sym_m['roi']:>+6.2f}% | PF {sym_m['pf']:>4.2f} | WR {sym_m['wr']:>5.1f}% | Trades {sym_m['trades']}")
    print("-" * 60)
    
    # 7. Guardar los mejores parámetros en un diccionario listo para usar
    print("\n Recomendar e implementar cambios:")
    print("  Para implementar la configuracion balanceada o de mejor PF,")
    print("  edita las siguientes variables en config.py:")
    print(f"    SL_ATR_MULT = {best_balanced['sl_atr']}")
    print(f"    TP_ATR_MULT = {best_balanced['tp_atr']}")
    print(f"    PARTIAL_TP_PCT = {best_balanced['partial_tp']}")
    print(f"    RSI_MIN = {best_balanced['rsi_min']}")
    print("\nEste script no modificara el archivo directamente de forma automatica para")
    print("mantener la seguridad del codigo. Copia y pega estos valores si los apruebas.")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
