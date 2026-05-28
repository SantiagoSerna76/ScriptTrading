document.addEventListener('DOMContentLoaded', () => {
    let pnlChart = null;
    let historyLength = 0;

    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
    const formatPct = (val) => `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`;

    window.runScanner = async function() {
        const btn = document.getElementById('btn-scan');
        btn.disabled = true;
        btn.innerHTML = '<span class="pulse" style="display:inline-block">🔄</span> Escaneando (30s)...';
        try {
            const res = await fetch('/api/scan', { method: 'POST' });
            const data = await res.json();
            console.log(data.message);
        } catch(e) {
            console.error('Error iniciando escáner:', e);
            alert('Error iniciando escáner de altcoins.');
        }
        // Rehabilitar botón luego de un tiempo prudencial (el escaneo tarda aprox 15-30s)
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = '🔄 Ejecutar Escáner';
            fetchConfig(); // Forzar actualización visual
        }, 15000);
    }

    async function fetchConfig() {
        try {
            const res = await fetch('/api/config');
            const data = await res.json();
            
            document.getElementById('last-scan-time').textContent = data.last_scan;
            
            const eliteContainer = document.getElementById('elite-badges');
            const sniperContainer = document.getElementById('sniper-badges');
            
            let htmlElite = '';
            if (data.elite_symbols && data.elite_symbols.length > 0) {
                data.elite_symbols.forEach(sym => {
                    htmlElite += `<span class="symbol-badge" style="background: rgba(16, 185, 129, 0.1); color: #10b981; border-color: rgba(16, 185, 129, 0.3);">${sym}</span>`;
                });
            } else {
                htmlElite = '<span class="symbol-badge" style="border-color:var(--danger); color:var(--danger)">Ninguno</span>';
            }
            eliteContainer.innerHTML = htmlElite;

            let htmlSniper = '';
            if (data.entry_symbols && data.entry_symbols.length > 0) {
                data.entry_symbols.forEach(sym => {
                    if (!data.elite_symbols || !data.elite_symbols.includes(sym)) {
                        htmlSniper += `<span class="symbol-badge">${sym}</span>`;
                    }
                });
                if (htmlSniper === '') {
                    htmlSniper = '<span class="symbol-badge" style="border-color:var(--text-muted); color:var(--text-muted)">Solo monedas élite</span>';
                }
            } else {
                htmlSniper = '<span class="symbol-badge" style="border-color:var(--danger); color:var(--danger)">Ninguno</span>';
            }
            sniperContainer.innerHTML = htmlSniper;
        } catch(e) {
            console.error('Error fetching config:', e);
        }
    }

    function initChart() {
        const ctx = document.getElementById('pnlChart').getContext('2d');
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Outfit', sans-serif";

        pnlChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'P&L Acumulado ($)',
                    data: [],
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#0f172a',
                    pointBorderColor: '#38bdf8',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleFont: { size: 14, family: "'Outfit', sans-serif" },
                        bodyFont: { size: 14, family: "'Outfit', sans-serif" },
                        padding: 12,
                        cornerRadius: 8,
                        displayColors: false
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            callback: function(value) { return '$' + value; }
                        }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    async function fetchStats() {
        try {
            const res = await fetch('/api/stats');
            const data = await res.json();

            const eTotal = document.getElementById('total-pnl');
            const eDaily = document.getElementById('daily-pnl');
            const eWR = document.getElementById('win-rate');
            const eTrades = document.getElementById('total-trades');

            eTotal.textContent = formatCurrency(data.total_pnl);
            eTotal.className = `value ${data.total_pnl >= 0 ? 'positive' : 'negative'}`;

            eDaily.textContent = formatCurrency(data.daily_pnl);
            eDaily.className = `value ${data.daily_pnl >= 0 ? 'positive' : 'negative'}`;

            eWR.textContent = `${data.win_rate.toFixed(1)}%`;
            eWR.classList.remove('loading');
            
            eTrades.textContent = `${data.total_trades}`;
            eTrades.classList.remove('loading');

        } catch (e) {
            console.error('Error fetching stats:', e);
        }
    }

    async function fetchOpenTrades() {
        try {
            const res = await fetch('/api/open_trades');
            const trades = await res.json();
            
            document.getElementById('open-count').textContent = trades.length;
            const tbody = document.getElementById('open-trades-body');
            
            if (trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No hay operaciones abiertas en este momento</td></tr>';
                return;
            }

            let html = '';
            trades.forEach(t => {
                const isBreakEven = t.trailing_sl >= t.entry_price;
                const slClass = isBreakEven ? 'positive' : 'negative';
                const tpClass = t.partial_exit_done ? 'positive' : 'text-muted';
                const tpText = t.partial_exit_done ? '✅ 50% Asegurado' : 'Esperando +1.5%';

                html += `
                    <tr>
                        <td><strong>${t.symbol}</strong></td>
                        <td>${formatCurrency(t.entry_price)}</td>
                        <td>${formatCurrency(t.stop_loss)}</td>
                        <td class="${slClass}">${formatCurrency(t.trailing_sl)} ${isBreakEven ? '🛡️' : ''}</td>
                        <td class="${tpClass}">${tpText}</td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        } catch (e) {
            console.error('Error fetching open trades:', e);
        }
    }

    async function fetchHistory() {
        try {
            const res = await fetch('/api/history');
            const trades = await res.json();
            
            const tbody = document.getElementById('history-body');
            
            if (trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No hay historial reciente</td></tr>';
                return;
            }

            let html = '';
            trades.forEach(t => {
                const isWin = t.pnl >= 0;
                const pnlClass = isWin ? 'positive' : 'negative';
                // Append 'Z' to treat the date as UTC, so toLocaleString converts it to the user's local timezone
                const dateString = t.time.endsWith('Z') ? t.time : t.time.replace(' ', 'T') + 'Z';
                const date = new Date(dateString).toLocaleString('es-ES', { month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit' });

                html += `
                    <tr>
                        <td><strong>${t.symbol}</strong><br><small style="color:var(--text-muted)">${date}</small></td>
                        <td>${formatCurrency(t.exit_price)}</td>
                        <td>${t.reason}</td>
                        <td class="${pnlClass}">${formatCurrency(t.pnl)}<br><small>${formatPct(t.percent)}</small></td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;

            // Update Chart if new trades exist
            if (trades.length !== historyLength) {
                historyLength = trades.length;
                updateChart(trades);
            }
        } catch (e) {
            console.error('Error fetching history:', e);
        }
    }

    function updateChart(trades) {
        // Reverse to chronological order
        const chronological = [...trades].reverse();
        let currentPnl = 0;
        
        const labels = ['Inicio'];
        const data = [0];

        chronological.forEach((t, i) => {
            currentPnl += t.pnl;
            labels.push(`Trade #${i+1}`);
            data.push(currentPnl);
        });

        pnlChart.data.labels = labels;
        pnlChart.data.datasets[0].data = data;
        
        // Color update based on final PNL
        const color = currentPnl >= 0 ? '#10b981' : '#f43f5e';
        const bgColor = currentPnl >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)';
        
        pnlChart.data.datasets[0].borderColor = color;
        pnlChart.data.datasets[0].pointBorderColor = color;
        pnlChart.data.datasets[0].backgroundColor = bgColor;

        pnlChart.update();
    }

    initChart();
    
    // Initial fetch
    fetchConfig();
    fetchStats();
    fetchOpenTrades();
    fetchHistory();

    // Poll every 5 seconds
    setInterval(() => {
        fetchConfig();
        fetchStats();
        fetchOpenTrades();
        fetchHistory();
    }, 5000);
});
