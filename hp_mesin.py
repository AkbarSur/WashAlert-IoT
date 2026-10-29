"""NODE 1: HP A, diletakkan di atas mesin cuci (edge1).

Di HP (Termux):  python hp_mesin.py
Di laptop:       python hp_mesin.py --source simulator   (simulasi satu siklus cuci)
"""

from shared.edge_runner import run_edge

if __name__ == "__main__":
    run_edge("edge1", default_scenario="washer")
