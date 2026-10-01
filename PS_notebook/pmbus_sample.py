"""Sample the ZCU104 PMBus rails for N seconds: python3 pmbus_sample.py <seconds> <tag> <out.csv>"""
import sys, time, csv
from pynq import get_rails
secs, tag, out = float(sys.argv[1]), sys.argv[2], sys.argv[3]
rails = get_rails(); rows = []; t_end = time.time() + secs
while time.time() < t_end:
    row = {"t": time.time(), "tag": tag}
    for n, r in rails.items():
        try: row[n] = float(r.power.value)
        except Exception: pass
    rows.append(row); time.sleep(0.25)
keys = ["t", "tag"] + sorted(k for k in rows[0] if k not in ("t", "tag"))
with open(out, "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys)
    if f.tell() == 0: w.writeheader()
    w.writerows(rows)
avg = {k: sum(r[k] for r in rows) / len(rows) for k in keys[2:]}
print(tag, {k: round(v, 3) for k, v in avg.items() if k in ("INT", "12V", "1V2", "1V8", "3V3")})
