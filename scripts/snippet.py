from config import DIRS
t = (DIRS["ley"] / "2020" / "02" / "programa.csv").read_bytes().decode("utf-8-sig", errors="replace")
for l in t.splitlines():
    c = l.split(";")
    if len(c) > 14 and c[3] == "50" and "Primera Categor" in l:
        print(l)