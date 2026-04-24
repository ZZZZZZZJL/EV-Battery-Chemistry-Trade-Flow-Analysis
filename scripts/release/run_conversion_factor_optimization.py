from __future__ import annotations

import argparse

from trade_flow.conversion_factor_optimization import run_conversion_factor_optimization


def _parse_stage_triplet(value: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in value.replace("-", ",").split(",") if part.strip()]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("stage triplet must look like S1,S2,S3")
    return parts[0], parts[1], parts[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metal", required=True, choices=["Li", "Ni", "Co"])
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--stage-triplet", required=True, type=_parse_stage_triplet)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--raw-import-root", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--cobalt-mode", default="mid", choices=["mid", "max", "min"])
    parser.add_argument("--solver-python", default=None)
    args = parser.parse_args()

    result = run_conversion_factor_optimization(
        metal=args.metal,
        year=args.year,
        stage_triplet=args.stage_triplet,
        website_root=args.project_root,
        raw_import_root=args.raw_import_root,
        output_root=args.output_root,
        cobalt_mode=args.cobalt_mode,
        solver_python=args.solver_python,
    )
    summary = result.summary_df.iloc[0]
    print("Conversion-factor optimization completed.")
    print(f"Output directory: {result.output_dir}")
    print(f"Solver backend: {summary['solver_backend']}")
    print(f"Baseline SN total: {summary['baseline_SN_total']:.6f}")
    print(f"Optimized SN total: {summary['optimized_SN_total']:.6f}")
    if summary["reduction_ratio"] == summary["reduction_ratio"]:
        print(f"Reduction ratio: {float(summary['reduction_ratio']):.6%}")
    print(f"c_pp vars (PP): {int(summary['number_of_c_pp_variables'])}")
    print(f"c_pn vars (PN): {int(summary['number_of_c_pn_variables'])}")
    print(f"c_np vars (NP): {int(summary['number_of_c_np_variables'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
