#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agente de monitoramento para TCC (v2 – consumo × carga × horas)

Este agente amplia o monitoramento para suportar, na prática, a demonstração de:
- correlação entre consumo e carga (desempenho como uso efetivo)
- relação horas de uso × consumo × desempenho
- discussão do trade-off energia–desempenho

Funcionalidades:
- Coleta CPU (média de 1s), RAM, memória disponível, SWAP
- Coleta disco por delta: taxas (B/s) e latência média (ms/op)
- Calcula carga efetiva (0–1) a partir de CPU, RAM e disco
- Estima potência e energia por intervalo (quando não houver medição direta):
    P(t) = P_idle + (P_active - P_idle) * L(t)
    E_Wh(t) = P(t) * (Δt/3600)
- Marca uso ativo por limiar de carga

Execução típica:
  $Env:AGENT_SALT='segredo'
  python agent_monitor_tcc_v2.py --interval 300 --duration 0 --phase baseline --outdir data
  python agent_monitor_tcc_v2.py --interval 300 --duration 0 --phase post --outdir data
"""

import argparse
import csv
import datetime as dt
import hashlib
import os
import platform
import time
from typing import Dict

import psutil

# -----------------------------
# Utilidades
# -----------------------------

def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def pseudonymize(text: str, salt: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update((salt + text).encode('utf-8'))
    return h.hexdigest()

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

# -----------------------------
# Disco por delta
# -----------------------------

class DiskSnapshot:
    def __init__(self):
        c = psutil.disk_io_counters()
        self.t = time.time()
        self.rb = c.read_bytes
        self.wb = c.write_bytes
        self.rc = c.read_count
        self.wc = c.write_count
        self.rt = getattr(c, 'read_time', 0.0)   # ms (cumulativo)
        self.wt = getattr(c, 'write_time', 0.0)  # ms (cumulativo)

    def delta(self) -> Dict[str, float]:
        c = psutil.disk_io_counters()
        t2 = time.time()
        dt_s = max(t2 - self.t, 1e-6)

        d_rb = max(c.read_bytes - self.rb, 0)
        d_wb = max(c.write_bytes - self.wb, 0)
        d_rc = max(c.read_count - self.rc, 0)
        d_wc = max(c.write_count - self.wc, 0)
        d_rt = max(getattr(c, 'read_time', 0.0) - self.rt, 0.0)
        d_wt = max(getattr(c, 'write_time', 0.0) - self.wt, 0.0)

        read_Bps = d_rb / dt_s
        write_Bps = d_wb / dt_s
        ops = d_rc + d_wc
        avg_lat_ms = (d_rt + d_wt) / ops if ops > 0 else 0.0

        self.t, self.rb, self.wb = t2, c.read_bytes, c.write_bytes
        self.rc, self.wc = c.read_count, c.write_count
        self.rt, self.wt = getattr(c, 'read_time', 0.0), getattr(c, 'write_time', 0.0)

        return {
            'disk_read_Bps': read_Bps,
            'disk_write_Bps': write_Bps,
            'disk_ops_read': d_rc,
            'disk_ops_write': d_wc,
            'disk_avg_latency_ms': avg_lat_ms,
            'interval_s': dt_s
        }

# -----------------------------
# Amostragem
# -----------------------------

def sample_cpu_mem() -> Dict[str, float]:
    # CPU com média de 1s para estabilidade
    cpu_pct = psutil.cpu_percent(interval=1.0)
    vm = psutil.virtual_memory()
    ram_pct = vm.percent
    mem_available_pct = (vm.available * 100.0 / vm.total) if vm.total else 0.0
    swap_pct = psutil.swap_memory().percent
    return {
        'cpu (%)': round(cpu_pct, 2),
        'ram (%)': round(ram_pct, 2),
        'mem_available (%)': round(mem_available_pct, 2),
        'swap (%)': round(swap_pct, 2)
    }

# -----------------------------
# Escrita CSV
# -----------------------------

def open_writer(path: str, fieldnames):
    is_new = not os.path.exists(path)
    f = open(path, 'a', newline='', encoding='utf-8')
    w = csv.DictWriter(f, fieldnames=fieldnames)
    if is_new:
        w.writeheader()
    return f, w

# -----------------------------
# Main
# -----------------------------

def main():
    parser = argparse.ArgumentParser(description='Agente TCC v2 – consumo × carga × horas')
    parser.add_argument('--interval', type=int, default=300, help='Segundos entre coletas (padrão=300)')
    parser.add_argument('--duration', type=int, default=0, help='Duração total em segundos (0=contínuo)')
    parser.add_argument('--outdir', type=str, default='data', help='Diretório de saída')
    parser.add_argument('--salt', type=str, default=os.getenv('AGENT_SALT', 'CHANGE-ME'), help='SALT para pseudonimização')

    parser.add_argument('--phase', choices=['baseline', 'post'], default='baseline', help='Rótulo do período')

    # Modelo de energia (estimativa)
    parser.add_argument('--p-idle', type=float, default=50.0, help='Potência idle (W)')
    parser.add_argument('--p-active', type=float, default=120.0, help='Potência carga alta (W)')

    # Carga efetiva
    parser.add_argument('--w-cpu', type=float, default=0.60)
    parser.add_argument('--w-ram', type=float, default=0.30)
    parser.add_argument('--w-disk', type=float, default=0.10)
    parser.add_argument('--disk-norm-mbps', type=float, default=50.0, help='Normalização do disco (MB/s)')
    parser.add_argument('--active-threshold', type=float, default=0.10, help='Limiar de uso ativo (0–1)')

    args = parser.parse_args()

    ensure_dir(args.outdir)

    os_name, os_release = platform.system(), platform.release()
    hostname = platform.node() or 'unknown-host'
    host_id = pseudonymize(hostname, args.salt)

    date_str = dt.datetime.now().strftime('%Y_%m_%d')
    csv_name = f'{date_str}_{args.phase}_{host_id}.csv'
    csv_path = os.path.join(args.outdir, csv_name)

    disk_norm_Bps = max(args.disk_norm_mbps, 1e-6) * 1024 * 1024
    w_sum = args.w_cpu + args.w_ram + args.w_disk
    w_cpu = args.w_cpu / w_sum
    w_ram = args.w_ram / w_sum
    w_disk = args.w_disk / w_sum

    fields = [
        'timestamp_utc', 'host_id', 'phase', 'os', 'os_release',
        'cpu (%)', 'ram (%)', 'mem_available (%)', 'swap (%)',
        'disk_read_Bps', 'disk_write_Bps', 'disk_ops_read', 'disk_ops_write', 'disk_avg_latency_ms',
        'interval_s',
        'load_cpu', 'load_ram', 'load_disk', 'load_effective',
        'active_flag',
        'power_w_est', 'energy_Wh_est', 'energy_kWh_cum'
    ]

    f, writer = open_writer(csv_path, fields)
    snap = DiskSnapshot()

    t0 = time.time()
    energy_cum_Wh = 0.0

    try:
        while True:
            if args.duration > 0 and (time.time() - t0) >= args.duration:
                break

            core = sample_cpu_mem()  # ~1s
            disk = snap.delta()      # dt_s real

            load_cpu = clamp01(core['cpu (%)'] / 100.0)
            load_ram = clamp01(core['ram (%)'] / 100.0)
            disk_Bps = max(disk['disk_read_Bps'] + disk['disk_write_Bps'], 0.0)
            load_disk = clamp01(disk_Bps / disk_norm_Bps)
            load_effective = clamp01(w_cpu*load_cpu + w_ram*load_ram + w_disk*load_disk)

            power_w = args.p_idle + (args.p_active - args.p_idle) * load_effective
            dt_s = disk['interval_s']
            energy_Wh = power_w * (dt_s / 3600.0)
            energy_cum_Wh += energy_Wh

            active_flag = 1 if load_effective >= args.active_threshold else 0

            row = {
                'timestamp_utc': now_utc_iso(),
                'host_id': host_id,
                'phase': args.phase,
                'os': os_name,
                'os_release': os_release,
                **core,
                'disk_read_Bps': round(disk['disk_read_Bps'], 2),
                'disk_write_Bps': round(disk['disk_write_Bps'], 2),
                'disk_ops_read': int(disk['disk_ops_read']),
                'disk_ops_write': int(disk['disk_ops_write']),
                'disk_avg_latency_ms': round(disk['disk_avg_latency_ms'], 2),
                'interval_s': round(dt_s, 3),
                'load_cpu': round(load_cpu, 4),
                'load_ram': round(load_ram, 4),
                'load_disk': round(load_disk, 4),
                'load_effective': round(load_effective, 4),
                'active_flag': active_flag,
                'power_w_est': round(power_w, 2),
                'energy_Wh_est': round(energy_Wh, 6),
                'energy_kWh_cum': round(energy_cum_Wh / 1000.0, 6)
            }

            writer.writerow(row)
            f.flush()

            time.sleep(max(0, args.interval - 1))

    finally:
        f.close()

if __name__ == '__main__':
    main()
