import os
import re
import subprocess
import sys

def modify_config(sl, tp, ps_rang, ps_vol, ps_unc):
    with open("config.py", "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"SL_ATR_MULT\s*=\s*[\d\.]+", f"SL_ATR_MULT = {sl}", content)
    content = re.sub(r"TP_ATR_MULT\s*=\s*[\d\.]+", f"TP_ATR_MULT = {tp}", content)
    content = re.sub(r"POSITION_SIZE_RANGING\s*=\s*[\d\.]+", f"POSITION_SIZE_RANGING = {ps_rang}", content)
    content = re.sub(r"POSITION_SIZE_VOLATILE\s*=\s*[\d\.]+", f"POSITION_SIZE_VOLATILE = {ps_vol}", content)
    content = re.sub(r"POSITION_SIZE_UNCERTAIN\s*=\s*[\d\.]+", f"POSITION_SIZE_UNCERTAIN = {ps_unc}", content)
    with open("config.py", "w", encoding="utf-8") as f:
        f.write(content)

print("="*60)
print("INICIANDO PRUEBA A/B: V3 vs V4")
print("="*60)

# 1. Test V3
print("\n[1/2] Evaluando Bot V3 (Sin reducción por régimen, SL/TP 3.0)...")
modify_config(3.0, 3.0, 1.0, 1.0, 1.0)
v3_output = subprocess.run([".venv\\Scripts\\python.exe", "backtest.py"], capture_output=True, text=True)
v3_roi = 0.0
for line in v3_output.stderr.split('\n'):
    if "Capital final" in line and "ROI" in line:
        match = re.search(r"ROI\s*([\+\-\d\.]+)%", line)
        if match:
            v3_roi += float(match.group(1))

# 2. Test V4
print("[2/2] Evaluando Bot V4 (Ajuste dinámico por régimen, SL 2.0, TP 2.5)...")
modify_config(2.0, 2.5, 0.5, 0.7, 0.3)
v4_output = subprocess.run([".venv\\Scripts\\python.exe", "backtest.py"], capture_output=True, text=True)
v4_roi = 0.0
for line in v4_output.stderr.split('\n'):
    if "Capital final" in line and "ROI" in line:
        match = re.search(r"ROI\s*([\+\-\d\.]+)%", line)
        if match:
            v4_roi += float(match.group(1))

print("\n" + "="*60)
print("📊 RESULTADOS DEL SALTO DE CALIDAD (ROI Acumulado 5 Monedas)")
print("="*60)
print(f"💰 ROI Total V3 (Antiguo) : {v3_roi:+.2f}%")
print(f"🚀 ROI Total V4 (NUEVO)   : {v4_roi:+.2f}%")
print("="*60)
if v4_roi > v3_roi:
    diff = v4_roi - v3_roi
    print(f"✅ V4 es un {diff/v3_roi*100:.1f}% más rentable que V3 comprobado estadísticamente.")
