#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente de monitoramento para TCC (versão refatorada)
- Coleta CPU (média de 1s), RAM, memória disponível, SWAP
- Calcula taxas e latência média de disco por delta de contadores
- Gera CSV com timestamp UTC por linha
- Pseudonimiza hostname via SALT (LGPD)
- Parâmetros por CLI: --interval, --duration, --outdir, --salt

Observações:
- cpu_percent(interval=1.0) bloqueia por ~1s e estabiliza a leitura
- disk_io_counters() retorna contadores cumulativos => usamos delta
- newline='' no open() evita linhas em branco no Windows
"""

import argparse
import csv
import datetime as dt
import hashlib
import os
import platform
import time
from typing import Dict

import psutil  # pip install psutil

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
        self.rt = getattr(c, 'read_time', 0.0)  # ms desde boot
        self.wt = getattr(c, 'write_time', 0.0) # ms desde boot

    def delta(self) -> Dict[str, float]:
        c = psutil.disk_io_counters()
        t2 = time.time()
        dt_s = max(t2 - self.t, 1e-6)

        d_rb = max(c.read_bytes - self.rb, 0)
        d_wb = max(c.write_bytes - self.wb, 0)
        d_rc = max(c.read_count - self.rc, 0)
        d_wc = max(c.write_count - self.wc, 0)
        d_rt = max(getattr(c, 'read_time', 0.0)  - self.rt, 0.0)  # ms
        d_wt = max(getattr(c, 'write_time', 0.0) - self.wt, 0.0)  # ms

        read_Bps  = d_rb / dt_s
        write_Bps = d_wb / dt_s
        ops = d_rc + d_wc
        avg_lat_ms = (d_rt + d_wt) / ops if ops > 0 else 0.0

        # atualiza estado
        self.t  = t2
        self.rb = c.read_bytes
        self.wb = c.write_bytes
        self.rc = c.read_count
        self.wc = c.write_count
        self.rt = getattr(c, 'read_time', 0.0)
        self.wt = getattr(c, 'write_time', 0.0)

        return {
            'disk_read_Bps': read_Bps,
            'disk_write_Bps': write_Bps,
            'disk_ops_read': d_rc,
            'disk_ops_write': d_wc,
            'disk_avg_latency_ms': avg_lat_ms
        }


# -----------------------------
# Amostragem
# -----------------------------

def sample_cpu_mem() -> Dict[str, float]:
    cpu_pct = psutil.cpu_percent(interval=1.0)  # média ~1s (bloqueante)
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
    parser = argparse.ArgumentParser(description='Agente de coleta para TCC')
    parser.add_argument('--interval', type=int, default=300, help='Segundos entre coletas (padrão=300)')
    parser.add_argument('--duration', type=int, default=0, help='Duração total em segundos (0=contínuo)')
    parser.add_argument('--outdir', type=str, default='data', help='Diretório de saída (padrão=data)')
    parser.add_argument('--salt', type=str, default=os.getenv('AGENT_SALT', 'CHANGE-ME'), help='SALT para pseudonimização')
    args = parser.parse_args()

    ensure_dir(args.outdir)

    os_name, os_release = platform.system(), platform.release()
    hostname = platform.node() or 'unknown-host'
    host_id = pseudonymize(hostname, args.salt)

    date_str = dt.datetime.now().strftime('%Y_%m_%d')
    csv_name = f'{date_str}_{host_id}.csv'
    csv_path = os.path.join(args.outdir, csv_name)

    fields = [
        'timestamp_utc', 'host_id', 'os', 'os_release',
        'cpu (%)', 'ram (%)', 'mem_available (%)', 'swap (%)',
        'disk_read_Bps', 'disk_write_Bps', 'disk_ops_read', 'disk_ops_write', 'disk_avg_latency_ms'
    ]

    f, writer = open_writer(csv_path, fields)

    snap = DiskSnapshot()
    t0 = time.time()

    try:
        while True:
            if args.duration > 0 and (time.time() - t0) >= args.duration:
                break

            core = sample_cpu_mem()              # ~1s aqui (CPU média)
            disk = snap.delta()                   # deltas

            row = {
                'timestamp_utc': now_utc_iso(),
                'host_id': host_id,
                'os': os_name,
                'os_release': os_release,
                **core,
                **disk
            }
            writer.writerow(row)
            f.flush()

            # Compensar ~1s já gasto no cpu_percent
            sleep_s = max(0, args.interval - 1)
            time.sleep(sleep_s)

    finally:
        f.close()


if __name__ == '__main__':
    main()
