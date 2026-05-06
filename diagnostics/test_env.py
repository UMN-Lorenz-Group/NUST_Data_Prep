import os
def load_env_file(path=".Env"):
    if not os.path.exists(path):
        print("No .Env file found")
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
load_env_file()
k = os.environ.get("ANTHROPIC_API_KEY", "")
print("Key found:", bool(k), "| prefix:", k[:12] if k else "NONE")
