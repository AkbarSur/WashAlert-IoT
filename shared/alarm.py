"""OUTPUT / AKTUATOR: reaksi HP B (pemilik) saat cucian selesai.

Di Android (Termux + Termux:API) HP bergetar dan menampilkan notifikasi.
Di laptop kode yang sama hanya mencetak ke terminal.
"""

import shutil
import subprocess


def _run_quietly(command: list[str]):
    try:
        subprocess.run(command, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[ALARM] Gagal menjalankan {command[0]}: {exc}")


def ring_alarm(alert: dict):
    minutes = alert.get("run_minutes", "?")
    reason = str(alert.get("reason", "Cucian selesai"))
    print(f"\n[EDGE2 | ALARM] {reason} (mesin bekerja {minutes} menit). "
          "Goyang HP ini untuk konfirmasi.\n")

    if shutil.which("termux-vibrate"):
        _run_quietly(["termux-vibrate", "-d", "1500"])
    if shutil.which("termux-notification"):
        _run_quietly([
            "termux-notification",
            "--id", "washalert",
            "--title", "WashAlert: cucian selesai!",
            "--content", f"{reason}. Mesin bekerja {minutes} menit. Goyang HP untuk konfirmasi.",
            "--priority", "high",
            "--sound",
        ])
