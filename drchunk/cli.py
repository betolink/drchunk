"""
Dr. Chunk — Command-line interface.
"""

from __future__ import annotations

import argparse
import sys

import drchunk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="drchunk",
        description="Extract chunking and codec metadata from HDF5/NetCDF4 files.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ---------- sample ----------
    sample_p = sub.add_parser("sample", help="Sample granules from a CMR collection")
    sample_p.add_argument(
        "collection", nargs="?", default=None,
        help="Collection concept ID or short name",
    )
    sample_p.add_argument(
        "--concept-id", "-c", default=None,
        help="CMR concept ID (e.g. C1234567890-PROV)",
    )
    sample_p.add_argument(
        "--short-name", "-s", default=None,
        help="Collection short name (e.g. MODIS_Terra_NDVI)",
    )
    sample_p.add_argument(
        "--freq", "-f", default="M",
        choices=["D", "W", "M", "Y"],
        help="Time-slice frequency: D=day, W=week, M=month, Y=year (default: M)",
    )
    sample_p.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible sampling",
    )
    sample_p.add_argument(
        "--output", "-o", default=None,
        help="Save sampled granules as JSON (default: print count to stdout)",
    )

    # ---------- info ----------
    info_p = sub.add_parser("info", help="Extract metadata from files")
    info_p.add_argument("paths", nargs="*", help="File paths or globs (omit to read JSON from stdin)")
    info_p.add_argument(
        "--output", "-o", default=None,
        help="Save results as CSV (default: print to stdout)",
    )
    info_p.add_argument(
        "--npartitions", "-n", type=int, default=None,
        help="Number of Dask partitions (default: one per file)",
    )

    # ---------- report ----------
    report_p = sub.add_parser("report", help="Generate a homogeneity report")
    report_p.add_argument("paths", nargs="*", help="File paths or globs (omit to read JSON from stdin)")
    report_p.add_argument(
        "--npartitions", "-n", type=int, default=None,
        help="Number of Dask partitions (default: one per file)",
    )
    report_p.add_argument(
        "--freq", "-f", default="M",
        choices=["D", "W", "M", "Y"],
        help="If sampling: time-slice frequency (default: M)",
    )

    # ---------- visualize ----------
    viz_p = sub.add_parser("visualize", help="Launch the interactive timeline widget")
    viz_p.add_argument("paths", nargs="*", help="File paths or globs (omit to read JSON from stdin)")
    viz_p.add_argument(
        "--npartitions", "-n", type=int, default=None,
        help="Number of Dask partitions (default: one per file)",
    )
    viz_p.add_argument(
        "--save", "-o", default=None,
        help="Save widget as standalone HTML file instead of launching browser",
    )
    viz_p.add_argument(
        "--freq", "-f", default="M",
        choices=["D", "W", "M", "Y"],
        help="If sampling: time-slice frequency (default: M)",
    )

    # ---------- run (sample + auto-pipe) ----------
    run_p = sub.add_parser("run", help="Sample + inspect + report in one pass")
    run_p.add_argument(
        "collection", nargs="?", default=None,
        help="Collection concept ID or short name",
    )
    run_p.add_argument(
        "--concept-id", "-c", default=None,
        help="CMR concept ID",
    )
    run_p.add_argument(
        "--short-name", "-s", default=None,
        help="Collection short name",
    )
    run_p.add_argument(
        "--freq", "-f", default="M",
        choices=["D", "W", "M", "Y"],
        help="Time-slice frequency (default: M)",
    )
    run_p.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible sampling",
    )
    run_p.add_argument(
        "--output", "-o", default=None,
        help="Save report to file (default: print to stdout)",
    )
    run_p.add_argument(
        "--npartitions", "-n", type=int, default=None,
        help="Number of Dask partitions (default: one per file)",
    )

    args = parser.parse_args(argv)

    if args.command == "sample":
        concept_id = args.concept_id or (
            args.collection if args.collection and "-" in args.collection else None
        )
        short_name = args.short_name or (
            args.collection if args.collection and "-" not in args.collection else None
        )
        if not concept_id and not short_name:
            parser.error("Provide --concept-id, --short-name, or a collection argument")

        granules = drchunk.sample(
            concept_id=concept_id,
            short_name=short_name,
            freq=args.freq,
            seed=args.seed,
        )
        if args.output:
            import json
            with open(args.output, "w") as f:
                json.dump(granules, f, default=str)
            print(f"Saved {len(granules)} granules → {args.output}")
        else:
            print(f"Sampled {len(granules)} granules")

    elif args.command == "info":
        paths = _resolve_paths(args.paths)
        df = drchunk.info(paths, npartitions=args.npartitions)
        if args.output:
            df.to_csv(args.output, index=False)
            print(f"Saved {len(df)} rows → {args.output}")
        else:
            print(df.to_string())

    elif args.command == "report":
        paths = _resolve_paths(args.paths)
        df = drchunk.info(paths, npartitions=args.npartitions)
        print(drchunk.report(df))

    elif args.command == "visualize":
        paths = _resolve_paths(args.paths)
        df = drchunk.info(paths, npartitions=args.npartitions)
        ct = drchunk._timeline.ChunkTimeline(df)
        if args.save:
            ct.save(args.save)
        else:
            ct.show()

    elif args.command == "run":
        concept_id = args.concept_id or (
            args.collection if args.collection and "-" in args.collection else None
        )
        short_name = args.short_name or (
            args.collection if args.collection and "-" not in args.collection else None
        )
        if not concept_id and not short_name:
            parser.error("Provide --concept-id, --short-name, or a collection argument")

        granules = drchunk.sample(
            concept_id=concept_id,
            short_name=short_name,
            freq=args.freq,
            seed=args.seed,
        )
        if not granules:
            print("No granules found.", file=sys.stderr)
            return 1

        df = drchunk.info(granules, npartitions=args.npartitions)
        report_text = drchunk.report(df)
        if args.output:
            with open(args.output, "w") as f:
                f.write(report_text)
            print(f"Report saved → {args.output}")
        else:
            print(report_text)

    return 0


def _resolve_paths(raw: list[str]) -> list[str]:
    """Support stdin JSON input when no paths are given."""
    if raw:
        import glob as glob_mod
        expanded = []
        for p in raw:
            matches = glob_mod.glob(p)
            expanded.extend(matches or [p])
        return expanded

    import json
    import sys
    data = json.load(sys.stdin)
    if isinstance(data, list):
        return data
    return [data]


if __name__ == "__main__":
    sys.exit(main())
