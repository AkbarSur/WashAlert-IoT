"""NODE 2: HP B milik pemilik (edge2). Bergetar saat cucian selesai;
goyang HP ini untuk konfirmasi bahwa cucian sudah diambil.

Di HP (Termux):  python hp_pemilik.py
Di laptop:       python hp_pemilik.py --source simulator   (goyang otomatis di detik ke-40)
"""

from shared.alarm import ring_alarm
from shared.edge_runner import run_edge

if __name__ == "__main__":
    run_edge("edge2", on_alert=ring_alarm, default_scenario="ack")
