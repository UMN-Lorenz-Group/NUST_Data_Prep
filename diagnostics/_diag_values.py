"""Quick diagnostic: print raw Claude response for one UT-00 / Ottawa_ONT location."""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8")

for line in open(".Env", encoding="utf-8"):
    line = line.strip()
    if line.startswith("sk-ant-"):
        os.environ["ANTHROPIC_API_KEY"] = line
        break

import anthropic
import pandas as pd

client = anthropic.Anthropic()

# Upload PDF
print("Uploading PDF...", flush=True)
with open("input_1980/1980_done.pdf", "rb") as f:
    resp = client.beta.files.upload(file=("1980_done.pdf", f, "application/pdf"))
file_id = resp.id
print(f"file_id: {file_id}", flush=True)

# Build CSV block for UT-00 / Ottawa, ONT
df = pd.read_csv("output_1980/validated/combined_1980_phenotypesTable_approved.csv")
sl = df[(df["Test"] == "UT-00") & (df["City"] == "Ottawa") & (df["State"] == "ONT")]
wide = sl.pivot_table(index="Strain", columns="Phenotype", values="Value", aggfunc="first").reset_index()
csv_block = wide.to_csv(index=False)
print(f"\nCSV block ({len(csv_block)} chars, {sl['Strain'].nunique()} strains):", flush=True)
print(csv_block, flush=True)

prompt = (
    "You are verifying extracted values from a NUST 1980 annual report PDF.\n"
    "Test: UT-00\nLocation: Ottawa, ONT\n\n"
    "Here are the extracted values (CSV):\n"
    + csv_block
    + '\nFind this table in the PDF and check each cell. List only discrepancies.\n'
    'Return valid JSON only (no markdown fences):\n'
    '{"discrepancies": []}\n'
)

print(f"\nPrompt length: {len(prompt)} chars", flush=True)
print("Sending to Claude...", flush=True)

msg = client.beta.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4000,
    messages=[{"role": "user", "content": [
        {"type": "document", "source": {"type": "file", "file_id": file_id}},
        {"type": "text", "text": prompt},
    ]}],
    betas=["files-api-2025-04-14"],
)

print(f"\nstop_reason : {msg.stop_reason}", flush=True)
print(f"content len : {len(msg.content)}", flush=True)
for i, blk in enumerate(msg.content):
    print(f"block[{i}] type={blk.type}", flush=True)
    if hasattr(blk, "text"):
        text = blk.text
        print(f"  len={len(text)}", flush=True)
        print(f"  FULL TEXT:\n{text}", flush=True)
        # Try fallback JSON extraction
        import re, json
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                print(f"\nFallback JSON extracted OK: {len(parsed.get('discrepancies',[]))} discrepancies", flush=True)
            except Exception as e:
                print(f"\nFallback extraction FAILED: {e}", flush=True)
        else:
            print("\nNo JSON object found in response", flush=True)
