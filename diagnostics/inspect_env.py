with open(".Env", encoding="utf-8") as f:
    lines = f.readlines()
print("Lines:", len(lines))
for i, l in enumerate(lines[:10]):
    print(repr(l[:80]))
