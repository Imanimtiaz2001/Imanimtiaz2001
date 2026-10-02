from pathlib import Path

from clearcv.examples import CASES, make_example

if __name__ == "__main__":
    output = Path("examples")
    output.mkdir(exist_ok=True)
    for case in CASES:
        (output / f"{case}.pdf").write_bytes(make_example(case))
    print(f"Generated {len(CASES)} synthetic PDFs")
